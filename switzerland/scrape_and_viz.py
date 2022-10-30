import os
import pprint as pp
import random
import time
import urllib
import logging
import warnings
from datetime import date, datetime
from os.path import join

logging.basicConfig(
    filename="scrape_and_viz.log",
    level=logging.INFO,
    format="%(asctime)s:%(levelname)s:%(message)s",
)
import gensim.downloader as api
import numpy as np
import pandas as pd
import plotly.express as px
import pyshorteners
import requests
import tensorflow_hub as hub
import texthero as hero
from bs4 import BeautifulSoup
from kneed import KneeLocator
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler


def save_jobs_to_excel(jobs_list: list, file_path: str, verbose=False):
    """
    save_jobs_to_excel takes a list of dictionaries, each containing a job posting and saves it to an excel file

    Args:
        jobs_list (list): list of dictionaries, each containing a job posting
        file_path (str): path to save the excel file to
        verbose (bool, optional): Defaults to False.

    Returns:
        pd.DataFrame: dataframe of the jobs_list
    """
    df = pd.DataFrame(jobs_list)
    df.to_excel(file_path)
    logging.info("saved the following to excel with filename {}: \n".format(file_path))

    if verbose:

        print(df.info())
    return df


def shorten_URL_bitly(
    long_url: str,
    ACCESS_TOKEN: str = "",
    max_sleep_time: int = 5,
    verbose=False,
):
    """
    shorten_URL_bitly takes a long url and returns a shortened url using the bitly API

                    requires free account / API token. https://bitly.com/

    Args:
        long_url (str): long url to shorten
        ACCESS_TOKEN (str, optional): bitly API token. Defaults to "".
        max_sleep_time (int, optional): max time to sleep between requests. Defaults to 5.
        verbose (bool, optional): Defaults to False.

    Returns:
        str: shortened url
    """

    time.sleep(random.randint(1, max_sleep_time))  # don't overload API

    try:
        s = pyshorteners.Shortener(api_key=ACCESS_TOKEN)
        short_url = s.bitly.short(long_url)

        if verbose:
            logging.info("Short URL is {}".format(short_url))
    except Exception as e:
        print("Error: {}".format(e))
        short_url = long_url

    return short_url


def text_first_N(text, num=40):
    """
    text_first_N takes a string and returns the first N characters

    Args:
        text (str): string to shorten
        num (int, optional): number of characters to return. Defaults to 40.

    Returns:
        str: first N characters of text
    """

    text = " ".join(text) if isinstance(text, list) else str(text)

    return text[:num] + "..." if len(text) > num else text


def find_optimal_k(
    input_matrix,
    d_title: str = "",
    top_end: int = 11,
    show_plot=False,
    write_image=False,
    output_path_full: str = None,
    verbose=False,
):
    """
    find_optimal_k takes a matrix and returns the optimal number of clusters using the elbow method

    Args:
        input_matrix (np.array): matrix to cluster
        d_title (str): title of the data
        top_end (int, optional): max number of clusters to test. Defaults to 11.
        show_plot (bool, optional): show plot of elbow method. Defaults to False.
        write_image (bool, optional): write plot to image. Defaults to False.
        output_path_full (str, optional): path to write image to. Defaults to None.
        verbose (bool, optional): Defaults to False.

    Returns:
        int: optimal number of clusters
    """
    logging.info(f"finding optimal k for {d_title}")
    if output_path_full is None:
        output_path_full = os.getcwd()
    scaler = StandardScaler()
    # texthero input data structure is weird.
    #  stole the below if/else from the source code behind TH kmeans fn
    # https://github.com/jbesomi/texthero/blob/master/texthero/representation.py

    if isinstance(input_matrix, pd.DataFrame):
        # fixes weird issues parsing a texthero edited text pd series
        logging.info("input matrix is a pd dataframe")
        input_matrix_coo = input_matrix.sparse.to_coo()
        input_matrix_for_vectorization = input_matrix_coo.astype("float64")
    else:
        input_matrix_for_vectorization = list(input_matrix)

    scaled_features = scaler.fit_transform(input_matrix_for_vectorization)
    kmeans_kwargs = {
        "init": "random",
        "n_init": 30,
        "max_iter": 300,
        "random_state": 42,
    }
    logging.info(f"finding optimal k with params: {kmeans_kwargs}")
    # A list holds the SSE values for each k
    sse = []
    for k in range(1, top_end):
        kmeans = KMeans(n_clusters=k, **kmeans_kwargs)
        kmeans.fit(scaled_features)
        sse.append(kmeans.inertia_)

    sse = []  # A list holds the SSE values for each k
    for k in range(1, top_end):
        kmeans = KMeans(n_clusters=k, **kmeans_kwargs)
        kmeans.fit(scaled_features)
        sse.append(kmeans.inertia_)

    kmeans_opt_df = pd.DataFrame(
        list(zip(range(1, top_end), sse)), columns=["Number of Clusters", "SSE"]
    )
    title_k = f"Elbow Method for Optimal k - {d_title}"
    f_k = px.line(
        kmeans_opt_df,
        x="Number of Clusters",
        y="SSE",
        title=title_k,
        template="presentation",
        height=600,
        width=800,
    )

    kl = KneeLocator(
        range(1, top_end), sse, curve="convex", direction="decreasing"
    )  # find the optimal k
    onk = kl.elbow

    if onk is None:
        warnings.warn(
            "No elbow found - Returning # of clusters as max allowed ( {} )".format(
                top_end
            )
        )
        return top_end

    elif onk == top_end:
        warnings.warn(
            "Elbow found at max allowed # of clusters ( {} ) - consider increasing top_end and re-running".format(
                top_end
            )
        )
    logging.info(f"optimal k is {onk}")
    if verbose:
        print("Optimal number of clusters is {}".format(onk))
    f_k.add_vline(x=onk)  # add vertical line to plotly

    if show_plot:
        f_k.show()

    if write_image:
        f_k.write_image(join(output_path_full, title_k + ".png"))

    return onk


def viz_job_data(
    viz_df: pd.DataFrame,
    text_col_name: str,
    save_plot=False,
    h: int = 720,
    verbose=False,
):
    """
    viz_job_data takes a dataframe and returns a plotly figure of the top 10 most common words

    Args:
        viz_df (pd.DataFrame): dataframe to visualize
        text_col_name (str): name of the column to visualize (must be a string)
        save_plot (bool, optional): save plot to image. Defaults to False.
        h (int, optional): height of plot. Defaults to 720. The width is scaled based on the height.
        verbose (bool, optional):  Defaults to False.

    Returns:
        None
    """
    today = date.today()
    # Month abbreviation, day and year
    td_str = today.strftime("%b-%d-%Y")

    if verbose:
        print("running viz_job_data")
    viz_df["tfidf"] = viz_df[text_col_name].pipe(hero.clean).pipe(hero.tfidf)

    viz_df["kmeans"] = viz_df["tfidf"].pipe(hero.kmeans, n_clusters=5).astype(str)

    viz_df["pca"] = viz_df["tfidf"].pipe(hero.pca)

    hv_list = [x for x in viz_df.columns if x not in ["tfidf", "kmeans", "pca"]]

    plot_title = td_str + " Vizualize Companies by {} Data".format(text_col_name)

    # reformat data so don't have to use built-in plotting

    df_split_pca = pd.DataFrame(viz_df["pca"].to_list(), columns=["pca_x", "pca_y"])
    viz_df.drop(columns="pca", inplace=True)  # drop original PCA column
    viz_df = pd.concat([viz_df, df_split_pca], axis=1)  # merge dataframes

    # plot pca data

    w = int(h * (4 / 3))
    labels = {"pca_x": "PCA X", "pca_y": "PCA Y", "kmeans": "KMeans Cluster"}
    fig_s = px.scatter(
        viz_df,
        x="pca_x",
        y="pca_y",
        color="kmeans",
        hover_data=hv_list,
        title=plot_title,
        labels=labels,
        height=h,
        width=w,
        template="plotly_dark",
    )
    fig_s.show()

    if save_plot:
        fig_s.write_html(plot_title + ".html", include_plotlyjs=True)
        logging.info("saved plotly figure to {}".format(plot_title + ".html"))

    logging.info("plotting complete" + plot_title)


def load_gensim_word2vec(
    word2vec_model: str = "'glove-wiki-gigaword-300", verbose=False
):

    logging.info("loading gensim word2vec model {}".format(word2vec_model))
    loaded_model = api.load(word2vec_model)

    logging.info("loaded data for word2vec - ", datetime.now())

    if verbose:
        # for more info or bug fixing
        wrdvecs = pd.DataFrame(loaded_model.vectors, index=loaded_model.key_to_index)
        logging.info("created dataframe from word2vec data- ", datetime.now())
        logging.info("dimensions of the df: \n", wrdvecs.shape)

    if verbose:
        print("testing gensim model...")
        test_string = "computer"
        vector = loaded_model.wv[test_string]

        print("The shape of string {} is: \n {}".format(test_string, vector.shape))
        print("test complete - ", datetime.now())

    return loaded_model


def get_vector_freetext(input_text: str, model, verbose: int = 0, cutoff: int = 2):
    """
    get_vector_freetext takes a string and returns a vector of the average word2vec vector for each word in the string

    Args:
        input_text (str): string to convert to vector
        model (gensim model): gensim model to use
        verbose (int, optional): Defaults to 0. 0 = no output, 1 shows you how many words were skipped, 2 tells you each individual skipped word and ^
        cutoff (int, optional): Defaults to 2. minimum word length to consider

    Returns:
        np.array: vector of the average word2vec vector for each word in the string
    """

    lower_it = input_text.lower()
    input_words = lower_it.split(" ")  # yes, this is an assumption
    usable_words = [word for word in input_words if len(word) > cutoff]

    list_of_vectors = []
    num_words_total = len(usable_words)
    num_excluded = 0

    for word in usable_words:
        try:
            this_vector = model.wv[word]
            list_of_vectors.append(this_vector)
        except:
            num_excluded += 1
            if verbose == 2:
                print("\nThe word/term {} is not in the model vocab.".format(word))
                logging.info("Excluding from representative vector")

    rep_vec = np.mean(list_of_vectors, axis=0)

    if verbose > 0:
        logging.info(
            "Computed representative vector. Excluded {} words out of {}".format(
                num_excluded, num_words_total
            )
        )

    return rep_vec


def viz_job_data_word2vec(
    viz_df: pd.DataFrame,
    text_col_name: str,
    save_plot=False,
    h: int = 720,
    query_name: str = "",
    show_text=False,
    max_clusters: int = 15,
):
    """
    viz_job_data_word2vec takes a dataframe and returns a plotly figure of the top 10 most common words

    Args:
        viz_df (pd.DataFrame): dataframe to visualize
        text_col_name (str): name of the column to visualize (must be a string)
        save_plot (bool, optional): save plot to image. Defaults to False.
        h (int, optional): height of plot. Defaults to 720. The width is scaled based on the height.
        query_name (str, optional): name of the original query (to use in the title). Defaults to "".
        show_text (bool, optional): plot text in the plot. Defaults to False.
        max_clusters (int, optional): maximum number of clusters to use. Defaults to 15 for interpretability.
    """
    today = date.today()
    td_str = today.strftime("%b-%d-%Y")  # date string

    viz_df["avg_vec"] = viz_df[text_col_name].apply(
        get_vector_freetext, args=(w2v_model,)
    )

    if len(viz_df["avg_vec"]) < max_clusters:
        max_clusters = len(viz_df["avg_vec"])

    kmeans_numC = find_optimal_k(
        viz_df["avg_vec"], d_title="word2vec-" + query_name, top_end=max_clusters
    )

    # complete k-means clustering + pca dim red. w/ avg_vec
    if kmeans_numC is None:
        kmeans_numC = 5

    viz_df["kmeans"] = (
        viz_df["avg_vec"]
        .pipe(
            hero.kmeans,
            n_clusters=kmeans_numC,
            algorithm="elkan",
            random_state=42,
            n_init=30,
        )
        .astype(str)
    )
    viz_df["pca"] = viz_df["avg_vec"].pipe(hero.pca)

    # generate list of column names for hover_data
    hv_list = [
        col
        for col in viz_df.columns
        if col not in ["avg_vec", "pca", "tfidf", "summary"]
    ]

    # reformat data so don't have to use texthero built-in plotting
    df_split_pca = pd.DataFrame(viz_df["pca"].to_list(), columns=["pca_x", "pca_y"])
    viz_df.drop(columns="pca", inplace=True)
    viz_df = pd.concat([viz_df, df_split_pca], axis=1)  # merge

    w = int(h * (4 / 3))
    labels = {"pca_x": "PCA X", "pca_y": "PCA Y", "kmeans": "KMeans Cluster"}
    if len(query_name) > 0:
        # user provided query_name so include
        plot_title = (
            td_str
            + " viz Jobs by '{}' via word2vec + pca".format(text_col_name)
            + " | "
            + query_name
        )
    else:
        plot_title = td_str + " viz Jobs by '{}' via word2vec + pca".format(
            text_col_name
        )

    if show_text:
        # adds company names to the plot if you want
        viz_df["companies_abbrev"] = viz_df["companies"].apply(text_first_N, num=15)
        graph_text_label = "companies_abbrev"
    else:
        graph_text_label = None

    # plot dimension-reduced data
    fig_w2v = px.scatter(
        viz_df,
        x="pca_x",
        y="pca_y",
        color="kmeans",
        hover_data=hv_list,
        title=plot_title,
        labels=labels,
        height=h,
        width=w,
        template="plotly_dark",
        text=graph_text_label,
    )
    fig_w2v.show()

    if save_plot:
        # saves the HTML file
        # auto-saving as a static image is a lil difficult so just click on the interactive
        # plot it generates
        _title = plot_title + query_name + "_" + text_col_name + ".html"
        logging.info("Saving plot as {}".format(_title))
        fig_w2v.write_html(
            _title,
            include_plotlyjs=True,
        )

    logging.info("plot generated - ", datetime.now())


def load_google_USE(url: str = "https://tfhub.dev/google/universal-sentence-encoder/4"):
    """
    load_google_USE loads the google USE model from the URL

    Args:
        url (str): URL to the model, defaults to "https://tfhub.dev/google/universal-sentence-encoder/4"

    Returns:
        [type]: [description]
    """
    """helper function to load the google USE model"""
    st = time.perf_counter()
    embed = hub.load(url)
    rt = round((time.perf_counter() - st) / 60, 2)
    logging.info("Loaded Google USE in {} minutes".format(rt))
    return embed


def vizjobs_googleUSE(
    viz_df,
    text_col_name,
    USE_embedding,
    save_plot=False,
    h=720,
    query_name="",
    show_text=False,
    viz_type="TSNE",
):
    today = date.today()
    # Month abbreviation, day and year
    td_str = today.strftime("%b-%d-%Y")

    # generate embeddings for google USE. USE_embedding MUST be passed in
    embeddings = USE_embedding(viz_df[text_col_name])  # create list from np arrays
    use = np.array(embeddings).tolist()  # add lists as dataframe column
    viz_df["use_vec"] = use

    # get optimal number of kmeans. limit max to 15 for interpretability
    max_clusters = 15
    if len(viz_df["use_vec"]) < max_clusters:
        max_clusters = len(viz_df["use_vec"])

    kmeans_numC = find_optimal_k(
        viz_df["use_vec"], d_title="google_USE-" + query_name, top_end=max_clusters
    )

    # complete k-means clustering + pca dim red. w/ use_vec
    if kmeans_numC is None:
        kmeans_numC = 5

    viz_df["kmeans"] = (
        viz_df["use_vec"]
        .pipe(
            hero.kmeans,
            n_clusters=kmeans_numC,
            algorithm="elkan",
            random_state=42,
            n_init=30,
        )
        .astype(str)
    )

    # use the vector for dimensionality reduction

    if viz_type.lower() == "tsne":
        viz_df["TSNE"] = viz_df["use_vec"].pipe(hero.tsne, random_state=42)
    else:
        viz_df["pca"] = viz_df["use_vec"].pipe(hero.pca)

    # generate list of column names for hover_data in the html plot

    hv_list = list(viz_df.columns)
    hv_list.remove("use_vec")

    if "tfidf" in hv_list:
        hv_list.remove("tfidf")
    if "pca" in hv_list:
        hv_list.remove("pca")
    if "TSNE" in hv_list:
        hv_list.remove("TSNE")
    if "summary" in hv_list:
        hv_list.remove("summary")

    # reformat data so don't have to use texthero built-in plotting

    if viz_type.lower() == "tsne":
        # TSNE reformat
        df_split_tsne = pd.DataFrame(
            viz_df["TSNE"].to_list(), columns=["tsne_x", "tsne_y"]
        )
        viz_df.drop(columns="TSNE", inplace=True)  # drop original PCA column
        viz_df = pd.concat([viz_df, df_split_tsne], axis=1)  # merge dataframes
    else:
        # PCA reformat
        df_split_pca = pd.DataFrame(viz_df["pca"].to_list(), columns=["pca_x", "pca_y"])
        viz_df.drop(columns="pca", inplace=True)  # drop original PCA column
        viz_df = pd.concat([viz_df, df_split_pca], axis=1)  # merge dataframes

    # set up plot pars (width, title, text)
    w = int(h * (4 / 3))

    if len(query_name) > 0:
        # user provided query_name so include
        plot_title = (
            td_str
            + " viz Jobs by '{}' via google USE + {}".format(text_col_name, viz_type)
            + " | "
            + query_name
        )
    else:
        plot_title = td_str + " viz Jobs by '{}' via google USE {}".format(
            text_col_name, viz_type
        )
    if show_text:
        # adds company names to the plot if you want
        viz_df["companies_abbrev"] = viz_df["companies"].apply(text_first_N, num=15)
        graph_text_label = "companies_abbrev"
    else:
        graph_text_label = None

    # setup labels (decides pca or tsne)
    if viz_type.lower() == "tsne":
        plt_coords = ["tsne_x", "tsne_y"]
    else:
        plt_coords = ["pca_x", "pca_y"]

    # plot dimension-reduced data

    viz_df.dropna(inplace=True)

    fig_use = px.scatter(
        viz_df,
        x=plt_coords[0],
        y=plt_coords[1],
        color="kmeans",
        hover_data=hv_list,
        title=plot_title,
        height=h,
        width=w,
        template="plotly_dark",
        text=graph_text_label,
    )
    fig_use.show()

    # save if requested

    if save_plot:
        # saves the HTML file
        # auto-saving as a static image is a lil difficult so just click on the interactive
        # plot it generates
        fig_use.write_html(
            plot_title + query_name + "_" + text_col_name + ".html",
            include_plotlyjs=True,
        )

    logging.info("plot generated - ", datetime.now())


def find_CHjobs_from(
    website,
    desired_characs,
    job_query,
    job_type=None,
    language=None,
    verbose=False,
    filename: str = None,
):
    """

    This function extracts all the desired characteristics of all new job postings
        of the title and location specified and returns them in single file.

    Parameters
    ----------

        - Website: to specify which website to search
            - (options: 'indeed' or 'indeed_default')
        - job_query: words that you want to narrow down the jobs to.
            - for example 'data'
        - job_type:
            - 'internship' or 'fulltime' or 'permanent'
        - language:
            - 'en' or 'de' or other languages.. 'fr'? ew
        - desired_characs: what columns of data do you want to extract? options are:
            - 'titles', 'companies', 'links', 'date_listed', 'summary'
        - Filename: name of the file to save the data to. If None, then it will default to date.today().strftime("%b-%d-%Y") + "_[raw]_scraped_jobs_CH.xls"

    """

    assert website in [
        "indeed",
        "indeed_default",
    ], "website not supported - use 'indeed' or 'indeed_default'"
    assert job_type in [
        "internship",
        "fulltime",
        "permanent",
        None,
    ], "job_type not supported - use 'internship', 'fulltime', or 'permanent'"
    assert (
        len(language) == 2
    ), "language not supported - use 'en' or 'de' or other languages.. 'fr'? ew"
    # TODO: add other variables to assert
    filename = (
        filename or date.today().strftime("%b-%d-%Y") + "_[raw]_scraped_jobs_CH.xls"
    )
    if website == "indeed":
        sp_search = load_indeed_jobs_CH(job_query, job_type=job_type, language=language)
        job_soup = sp_search.get("job_soup")
        URL_used = sp_search.get("query_URL")

        if verbose:
            print("\n The full HTML docs are: \n")
            pp.pprint(job_soup, compact=True)
        jobs_list, num_listings = extract_job_information_indeedCH(
            job_soup, desired_characs, uURL=URL_used
        )
    elif website == "indeed_default":
        sp_search = load_indeed_jobs_CH(job_query, run_default=True)
        job_soup = sp_search.get("job_soup")
        URL_used = sp_search.get("query_URL")
        if verbose:
            print("\n The full HTML docs are: \n")
            pp.pprint(job_soup, compact=True)

        jobs_list, num_listings = extract_job_information_indeedCH(
            job_soup, desired_characs, uURL=URL_used
        )

    job_df = save_jobs_to_excel(jobs_list, filename)

    logging.info(
        "{} new job postings retrieved from {}. Stored in {}.".format(
            num_listings, website, filename
        )
    )

    return job_df


def load_indeed_jobs_CH(
    job_query, job_type=None, language: str = None, run_default=False
):
    i_website = "https://ch.indeed.com/Stellen?"
    def_website = "https://ch.indeed.com/Stellen?q=Switzerland+English&jt=internship"
    if run_default:
        # switzerland has a unique page shown below, can run by default
        # website = "https://ch.indeed.com/Switzerland-English-Jobs"

        getVars = {"fromage": "last", "limit": "50", "sort": "date"}

        url = def_website + urllib.parse.urlencode(getVars)
        page = requests.get(url)
        soup = BeautifulSoup(page.content, "html.parser")
        job_soup = soup.find(id="resultsCol")
    else:
        getVars = {
            "q": job_query,
            "jt": job_type,
            "lang": language,
            "fromage": "last",
            "limit": "50",
            "sort": "date",
        }

        # if values are not specified, then remove them from the dict (and URL)
        if job_query is None:
            del getVars["q"]
        if job_type is None:
            del getVars["jt"]
        if language is None:
            del getVars["lang"]

        url = i_website + urllib.parse.urlencode(getVars)
        page = requests.get(url)
        soup = BeautifulSoup(page.content, "html.parser")
        job_soup = soup.find(id="resultsCol")

    # return the job soup

    soup_results = {"job_soup": job_soup, "query_URL": url}
    return soup_results


def_URL = "https://ch.indeed.com/Stellen?" + "ADD_queries_here"


def extract_job_information_indeedCH(
    job_soup, desired_characs, uURL=def_URL, verbose=False, print_all=False
):
    # job_elems = job_soup.find_all('div', class_='mosaic-zone-jobcards')
    job_elems = job_soup.find_all("div", class_="job_seen_beacon")

    if print_all:
        print("\nAll found 'job elements' are as follows: \n")
        pp.pprint(job_elems, compact=True)

    with open("job_elements.txt", "w") as f:
        # save to text file for investigation
        logging.info(job_elems, file=f)

    cols = []
    extracted_info = []

    if "titles" in desired_characs:
        titles = []
        cols.append("titles")
        for job_elem in job_elems:
            titles.append(extract_job_title_indeed(job_elem, verbose=verbose))
        extracted_info.append(titles)

    if "companies" in desired_characs:
        companies = []
        cols.append("companies")
        for job_elem in job_elems:
            companies.append(extract_company_indeed(job_elem))
        extracted_info.append(companies)

    if "date_listed" in desired_characs:
        dates = []
        cols.append("date_listed")
        for job_elem in job_elems:
            dates.append(extract_date_indeed(job_elem))
        extracted_info.append(dates)

    if "summary" in desired_characs:
        summaries = []
        cols.append("summary")
        for job_elem in job_elems:
            summaries.append(extract_summary_indeed(job_elem))
        extracted_info.append(summaries)

    if "links" in desired_characs:
        links = []
        cols.append("links")
        for job_elem in job_elems:
            links.append(extract_link_indeedCH(job_elem, uURL))
        extracted_info.append(links)

    jobs_list = {}

    for j in range(len(cols)):
        jobs_list[cols[j]] = extracted_info[j]

    num_listings = len(extracted_info[0])

    return jobs_list, num_listings


def extract_job_title_indeed(job_elem, verbose=False):
    title_elem = job_elem.select_one("span[title]").text
    if verbose:
        logging.info(title_elem)
    try:
        title = title_elem.strip()
    except:
        title = "no title"
    return title


def extract_company_indeed(job_elem):
    company_elem = job_elem.find("span", class_="companyName")
    company = company_elem.text.strip()
    return company


def extract_link_indeedCH(job_elem, uURL):
    # some manual shenanigans occur here
    # working example https://ch.indeed.com/Stellen?q=data&jt=internship&lang=en&vjk=49ed864bd5e422fb

    link = job_elem.find("a")["href"]
    uURL_list = uURL.split("&fromage=last")
    link = uURL_list[0] + "&" + link
    # replace some text so that the link has a virtual job key. Found via trial and error
    return link.replace("/rc/clk?jk=", "vjk=")


def extract_date_indeed(job_elem):
    """
    extract_date_indeed extracts the date the job was posted

    Args:
        job_elem (bs4.element.Tag): bs4 element containing the job information

    Returns:
        date (str): date the job was posted
    """
    date_elem = job_elem.find("span", class_="date")
    date = date_elem.text.strip()
    return date


def extract_summary_indeed(job_elem):
    summary_elem = job_elem.find("div", class_="job-snippet")
    summary = summary_elem.text.strip()
    return summary


def indeed_postprocess(
    i_df, query_term, query_jobtype, verbose=False, shorten_links=False
):
    logging.info("Starting postprocess - ", datetime.now())

    # apply texthero cleaning
    i_df["titles"] = hero.clean(i_df["titles"])
    i_df["summary"] = hero.clean(i_df["summary"])

    # use bit.ly to shorten links
    if shorten_links:
        try:
            len(i_df["short_link"])
            logging.info("found values for short_link, not-recreating")
        except:
            logging.info("no values exist for short_link, creating them now")
            # there is a random delay to not overload APIs, max rt is 5s * num_rows
            i_df["short_link"] = i_df["links"].apply(shorten_URL_bitly)
    else:
        i_df["short_link"] = "not_created"

    # save file to excel
    rn = datetime.now()
    i_PP_date = rn.strftime("_%m.%d.%Y-%H-%M_")
    i_df["date_pulled"] = rn.strftime("%m.%d.%Y")
    i_df["time_pulled"] = rn.strftime("%H:%M:%S")
    out_name = (
        "JS_DB_"
        + "query=[term(s)="
        + query_term
        + ", type="
        + query_jobtype
        + "]"
        + i_PP_date
        + ".xlsx"
    )
    i_df.to_excel(out_name)
    if verbose:
        logging.info("Saved {} - ".format(out_name), datetime.now())

    # download if requested
    return i_df


def indeed_datatable(i_df, count_what="companies", freq_n=10):
    # basically just wrote this to reduce code down below
    # depends on the colab data_table.DataTable()

    logging.info("Count of column '{}' appearances in search:\n".format(count_what))
    comp_list_1 = i_df[count_what].value_counts()
    pp.pprint(comp_list_1.head(freq_n), compact=True)

    i_df_disp = i_df.copy()
    i_df_disp["summary_short"] = i_df_disp["summary"].apply(text_first_N)
    i_df_disp.drop(columns=["links", "summary"], inplace=True)  # drop verbose columns

    return i_df_disp


# define whether or not to shorten links
shorten_key = False  # @param {type:"boolean"}
# define whether or not to download excel versions of the files
# download_key = for specific searches deemed relevant
# download_all includes all searches
download_key = True  # @param {type:"boolean"}
download_all = False  # @param {type:"boolean"}

# determines columns in output dataframe post-scraping
desired_characs = ["titles", "companies", "links", "date_listed", "summary"]

if __name__ == "__main__":
    output_folder_path = os.getcwd()

    using_google_USE = True
    using_gensim_w2v = False

    # only load models declared as used
    today = date.today()
    # Month abbreviation, day and year
    d4 = today.strftime("%b-%d-%Y")

    default_filename = d4 + "_[raw]_scraped_jobs_CH.xls"

    if using_google_USE:
        meine_embeddings = load_google_USE()

    if using_gensim_w2v:
        w2v_model = load_gensim_word2vec()

    jq1 = "data"  # @param {type:"string"}
    jt1 = "internship"  # @param {type:"string"}
    lan = "en"  # @param {type:"string"}

    # variables for fn defined in form above

    chdf1 = find_CHjobs_from(
        website="indeed",
        desired_characs=desired_characs,
        job_query=jq1,
        job_type=jt1,
        language=lan,
    )

    q1_processed = indeed_postprocess(
        chdf1, query_term=jq1, query_jobtype=jt1, shorten_links=shorten_key
    )

    indeed_datatable(q1_processed)

    """**Viz Query 1**"""

    viz1_df = q1_processed.copy()
    viz1_df.drop(columns=["links", "short_link"], inplace=True)

    if using_google_USE:

        # general rule - if # of jobs returned > 25 may want to turn off text in
        # one or both plots (summary text and title text)

        vizjobs_googleUSE(
            viz1_df,
            "summary",
            meine_embeddings,
            save_plot=True,
            show_text=True,
            query_name=jt1 + " in " + jq1,
            viz_type="pca",
        )

        vizjobs_googleUSE(
            viz1_df,
            "titles",
            meine_embeddings,
            save_plot=True,
            show_text=False,
            query_name=jt1 + " in " + jq1,
            viz_type="pca",
        )
    else:
        viz_job_data_word2vec(
            viz1_df,
            "summary",
            save_plot=True,
            h=720,
            query_name=jt1 + " in " + jq1,
            viz_type="pca",
        )
        viz_job_data_word2vec(
            viz1_df,
            "titles",
            save_plot=True,
            h=720,
            query_name=jt1 + " in " + jq1,
            viz_type="pca",
        )

    # query 2 - all jobs in Switzerland for English Speakers

    jq2 = "indeed_default"  # passing this phrase in causes it to search for all en jobs
    jt2 = "all"
    # in the case of "run the special case on Indeed" query terms don't matter
    chdf2 = find_CHjobs_from(
        website="indeed_default", job_query="gimme", desired_characs=desired_characs
    )

    q2_processed = indeed_postprocess(
        chdf2, query_term=jq2, query_jobtype=jt2, shorten_links=False
    )

    indeed_datatable(q2_processed)

    """**Viz Query 2**"""

    viz_q2 = q2_processed.copy()
    viz_q2.drop(columns="links", inplace=True)

    if using_google_USE:

        # general rule - if # of jobs returned > 25 may want to turn off text in
        # one or both plots (summary text and title text)

        vizjobs_googleUSE(
            viz_q2,
            "summary",
            meine_embeddings,
            save_plot=True,
            show_text=True,
            query_name="all listings for CH eng. jobs",
            viz_type="tsne",
        )

        vizjobs_googleUSE(
            viz_q2,
            "titles",
            meine_embeddings,
            save_plot=True,
            show_text=False,
            query_name="all listings for CH eng. jobs",
            viz_type="tsne",
        )
    else:
        viz_job_data_word2vec(
            viz_q2,
            "summary",
            save_plot=False,
            h=720,
            query_name="all listings for CH eng. jobs",
            viz_type="tsne",
        )
        viz_job_data_word2vec(
            viz_q2,
            "titles",
            save_plot=False,
            h=720,
            query_name="all listings for CH eng. jobs",
            viz_type="tsne",
        )
