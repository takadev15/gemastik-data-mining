from typing import Any
from src.database.database import Database
from src.crawling.crawl_utils import CrawlUtils
from src.crawling.crawl_utils import CustomThreadPoolExecutor
from datetime import datetime
from urllib.parse import urljoin
import bs4
import threading
import queue
import time
import re


class BreadthFirstSearch:
    """
    Kelas yang digunakan untuk melakukan crawling dengan metode Breadth First Search.

    Args:
        crawl_id (int): ID crawling (table crawling di database)
        url_queue (queue.Queue): Kumpulan URL antrian
        visited_urls (list): Kumpulan URL yang sudah dikunjungi
        duration_sec (int): Durasi BFS crawler dalam detik
        max_threads (int): Maksimal threads yang akan digunakan
    """

    def __init__(
        self, crawl_id: int, url_queue: queue.Queue, visited_urls: list, duration_sec: int, max_threads: int
    ) -> None:
        self.crawl_id = crawl_id
        self.url_queue = url_queue
        self.visited_urls = visited_urls
        self.duration_sec = duration_sec
        self.max_threads = max_threads
        self.db = Database()
        self.crawl_utils = CrawlUtils()
        self.lock = threading.Lock()
        self.start_time: float = time.time()
        self.list_urls = []
        self.whitelist_domain = [
            "farmanddairy",
        ]

    def run(self) -> None:
        """
        Fungsi utama yang berfungsi untuk menjalankan proses crawling BFS.
        """
        executor = CustomThreadPoolExecutor(max_workers=self.max_threads)

        futures = []
        while True:
            try:
                time_now = time.time() - self.start_time
                time_now_int = int(time_now)
                if time_now_int >= self.duration_sec:
                    print("Stopped because exceeded time limit...")
                    break
                target_url = self.url_queue.get(timeout=60)
                if target_url not in self.visited_urls:
                    self.visited_urls.append(target_url)
                    futures.append(executor.submit(self.scrape_page, target_url))
            except queue.Empty:
                if self.crawl_utils.running_thread_count(futures) > 0:
                    continue
                else:
                    print("Stopped because empty queue...")
                    break
            except KeyboardInterrupt:
                print("Stopped because keyboard interrupt...")
                break
            except Exception as e:
                print(e)
                continue

        executor.shutdown39(wait=False, cancel_futures=True)

    def scrape_page(self, url: str) -> None:
        """
        Fungsi untuk menyimpan konten yang ada pada suatu halaman ke database.

        Args:
            url (str): URL halaman yang ingin discrape
        """
        try:
            page_start_time = time.time()
            response = self.crawl_utils.get_page(url)
            strip_domain = url.split(".")[1]
            if response and response.status_code == 200:
                db_connection = self.db.connect()
                self.lock.acquire()
                now = datetime.now()
                print(url, "| BFS |", now.strftime("%d/%m/%Y %H:%M:%S"))
                self.lock.release()
                soup = bs4.BeautifulSoup(response.text, "html.parser")
                title = soup.title.string
                article_html5 = soup.find("article")
                if article_html5 is None:
                    # extract text content from html4
                    html5 = 0
                    texts = soup.find("body").findAll(text=True)
                    visible_texts = filter(self.tag_visible, texts)
                    text = " ".join(t.strip() for t in visible_texts)
                    text = text.lstrip().rstrip()
                    text = text.split(",")
                    clean_text = ""
                    for sen in text:
                        if sen:
                            sen = sen.rstrip().lstrip()
                            clean_text += sen + ","
                    complete_text = clean_text
                else:
                    # extract text content from html5
                    html5 = 1
                    texts = article_html5.findAll(text=True)
                    visible_texts = filter(self.tag_visible, texts)
                    text = " ".join(t.strip() for t in visible_texts)
                    text = text.lstrip().rstrip()
                    text = text.split(",")
                    clean_text = ""
                    for sen in text:
                        if sen:
                            sen = sen.rstrip().lstrip()
                            clean_text += sen + ","
                    complete_text = clean_text

                # get meta description
                description = soup.find("meta", attrs={"name": "description"})
                if description is None:
                    description = "-"
                else:
                    description = description.get("content")

                # get meta keywords
                keywords = soup.find("meta", attrs={"name": "keywords"})
                if keywords is None:
                    keywords = "-"
                else:
                    keywords = keywords.get("content")

                # get tags
                # Hanya jalan untuk situs Thehill.com
                # tags = ""
                # try:
                #     for tag in soup.findAll("a", attrs={"class": "tags__item"}):
                #         tags += tag.string
                # except Exception as e:
                #     tags = "-"

                # get article
                # Hanya jalan untuk situs Thehill.com
                # content_article = ""
                # try:
                #     content_article = soup.find("div", attrs={"class": "article__text"}).get_text()
                # except Exception as e:
                #     content_article = None

                # For farmanddairy.com 
                content_article = ""
                try:
                    content_article = soup.find("div", attrs={"class": "td-post-content"}).get_text()
                except Exception as e:
                    content_article = None

                # For farmweeknow.com
                # content_article = ""
                # try:
                #     content_article = soup.find("div", attrs={"class": "asset-content"}).get_text()
                # except Exception as e:
                #     content_article = None

                # isHotURL
                hot_link = 0

                # check if the page information already exist
                if self.db.check_value_in_table(db_connection, "page_information", "url", url):
                    self.db.close_connection(db_connection)
                    return

                # size of the page
                size_bytes = len(response.content)

                page_id = self.crawl_utils.insert_page_information(
                    db_connection,
                    url,
                    self.crawl_id,
                    html5,
                    title,
                    description,
                    keywords,
                    content_article,                    
                    complete_text,
                    hot_link,
                    size_bytes,
                    "BFS crawling",
                    0,
                )

                # extract outgoing link
                links = soup.findAll("a", href=True)
                for i in links:
                    # Complete relative URLs and strip trailing slash
                    complete_url = urljoin(url, i["href"]).rstrip("/")

                    self.list_urls.append(complete_url)  # For  MSB
                    self.crawl_utils.insert_page_linking(db_connection, page_id, complete_url)

                    self.lock.acquire()
                    print(strip_domain)
                    if self.crawl_utils.is_valid_url(complete_url) and complete_url not in self.visited_urls and strip_domain in self.whitelist_domain:
                        self.url_queue.put(complete_url)
                    self.lock.release()

                # extract tables
                # try:
                #     for table in soup.findAll("table"):
                #         self.crawl_utils.insert_page_table(db_connection, page_id, table)
                # except:
                #     pass

                # # extract lists
                # try:
                #     for lists in soup.findAll("li"):
                #         self.crawl_utils.insert_page_list(db_connection, page_id, lists)
                # except:
                #     pass

                # # extract forms
                # try:
                #     for form in soup.findAll("form"):
                #         self.crawl_utils.insert_page_form(db_connection, page_id, form)
                # except:
                #     pass

                # # extract paragraphs
                # try:
                #     for paragraph in soup.findAll("p"):
                #         self.crawl_utils.insert_page_paragraph(db_connection, page_id, paragraph)
                # except:
                #     pass
                
                # extract tags
                # Dari thehill.com
                # try:
                #     for tag in soup.findAll("a", attrs={"class": "tags__item"}):
                #         tag_string = tag.string.replace('\t', '')
                #         tag_string = tag_string.replace('\n', '')
                #         tag_string = tag_string.lower()
                #         self.crawl_utils.insert_page_tag(db_connection, page_id, tag_string)
                # except:
                #     pass

                # For farmanddiary
                try:
                    ul_prop = soup.find("ul", attrs={"class": "td-tags"})
                    for tag in ul_prop.findAll("a"):
                        tag_string = tag.string.replace('\t', '')
                        tag_string = tag_string.replace('\n', '')
                        tag_string = tag_string.lower()
                        self.crawl_utils.insert_page_tag(db_connection, page_id, tag_string)
                except:
                    pass

                # For farmweeknow
                # try:
                #     div_prop = soup.find("div", attrs={"class": "asset-tags"})
                #     for tag in div_prop.findAll("a"):
                #         tag_string = tag.string.replace('\t', '')
                #         tag_string = tag_string.replace('\n', '')
                #         tag_string = tag_string.lower()
                #         self.crawl_utils.insert_page_tag(db_connection, page_id, tag_string)
                # except:
                #     pass

                # try:
                #     # extract images
                #     for image in soup.findAll("img"):
                #         self.crawl_utils.insert_page_image(db_connection, page_id, image)
                # except:
                #     pass

                # try:
                #     # extract style
                #     for style in soup.findAll("style"):
                #         self.crawl_utils.insert_page_style(db_connection, page_id, style)
                # except:
                #     pass

                # try:
                #     # extract script
                #     for script in soup.findAll("script"):
                #         self.crawl_utils.insert_page_script(db_connection, page_id, script)
                # except:
                #     pass

                page_duration_crawl = time.time() - page_start_time
                self.crawl_utils.update_page_duration_crawl(db_connection, page_id, page_duration_crawl)
                self.db.close_connection(db_connection)
                return
            return
        except Exception as e:
            print(e, "~ Error in thread")
            return

    def tag_visible(self, element: Any) -> bool:
        """
        Fungsi untuk merapihkan konten teks.

        Args:
            element (Any): Elemen HTML
        """
        if element.parent.name in ["style", "script", "head", "title", "meta", "[document]"]:
            return False
        if isinstance(element, bs4.element.Comment):
            return False
        if re.match(r"[\n]+", str(element)):
            return False
        return True
