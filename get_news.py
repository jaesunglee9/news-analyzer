#!/usr/bin/env python
# coding: utf-8

# In[77]:


import time
import requests
import datetime
import lxml
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import codecs
import re
import json

import sqlite3
import chromadb


# In[78]:


def get_news_date(date_format="%Y%m%d"):
    """
    Determines the "news date" based on the current time.

    The "news day" is considered to change at 10 PM (22:00).
    - If the current time is 10 PM or later, it returns today's date.
    - If the current time is before 10 PM, it returns yesterday's date.

    Args:
        date_format (str, optional): The format for the output date string,
                                     using standard strftime codes.
                                     Defaults to "%Y%m%d".

    Returns:
        str: The formatted date string for the relevant news day.
    """
    # Get the current date and time
    now = datetime.datetime.now()

    # The cutoff hour is 10 PM, which is 22 in 24-hour format
    cutoff_hour = 22

    # Check if the current hour is past the cutoff time
    if now.hour >= cutoff_hour:
        # It's 10 PM or later, so the news day is today
        target_date = datetime.date.today()
    else:
        # It's before 10 PM, so we should be looking at yesterday's news
        target_date = datetime.date.today() - datetime.timedelta(days=1)

    # Format the determined date into the desired string format
    return target_date.strftime(date_format)


# In[79]:


# Prep hard codes and session
date = get_news_date()
kbs_program_url = f"https://news.kbs.co.kr/news/pc/program/program.do?bcd=0001&ref=pGnb#{date}"
mbc_program_url = f"https://imnews.imbc.com/replay/2025/nwdesk/"
sbs_program_url = f"https://news.sbs.co.kr/news/programMain.do?prog_cd=R1&broad_date={date}&plink=CAL&cooper=SBSNEWS"

session = requests.Session()


# In[80]:


# Selenium setup
options = webdriver.FirefoxOptions()
options.add_argument("--headless")

geckodriver_path = "/home/user0/tmp/geckodriver"
service = webdriver.FirefoxService(executable_path=geckodriver_path)
driver = webdriver.Firefox(service=service, options=options)


# In[14]:


def get_kbsnews(url, session):
    response = session.get(url)
    soup = BeautifulSoup(response.text, 'lxml')
    script_tag = soup.find('script', string=re.compile(r"var messageText"))
    pattern = re.compile(r'var messageText = "(.*?)";', re.DOTALL)
    match = pattern.search(script_tag.text)
    content = match.group(1)
    news_soup = BeautifulSoup(content, 'lxml')
    text = news_soup.get_text(separator="\n", strip=True)
    text = text.replace("\\", "")
    pattern = r"\nKBS 뉴스 [가-힣]+입니다\.[\s\S]*"
    cleaned_text = re.sub(pattern, "", text).strip()
    return cleaned_text


# In[27]:


def get_kbs_newslist(date, kbs_program_url, driver, session):
    # Get Selenium driver response of kbs news url
    driver.get(kbs_program_url)
    wait = WebDriverWait(driver, 15)
    wait.until(EC.presence_of_element_located((By.CLASS_NAME, "box-content")))

    # Get html elements containing label box-content
    kbs_source = driver.page_source
    kbs_soup = BeautifulSoup(kbs_source, 'lxml')
    kbs_items = kbs_soup.select("a.box-content")

    # make initial list
    kbs_base_url = "https://news.kbs.co.kr"
    kbs_boxlist = []
    for item in kbs_news_items:
        title = item.find('p', class_='title').get_text(strip=True) if item.find('p', class_='title') else "N/A"
        relative_link = item.get('href')
        full_link = urljoin(kbs_base_url, relative_link)
        kbs_boxlist.append({'title': title, 'url': full_link, 'broadcast_date': date})

    # Remove empty elements and sports
    isNews = False
    kbs_newslist = []
    for i in range(len(kbs_boxlist)):
        if kbs_boxlist[i]['title'] == '오프닝':
            isNews = True
            continue
        if isNews == False:
            continue
        else:
            if kbs_boxlist[i]['title'] == '[스포츠9 헤드라인]':
                isNews = False
                continue
            kbs_newslist.append(kbs_boxlist[i])

    # add index 
    for i in range(len(kbs_newslist)):
        kbs_newslist[i]['order'] = i + 1

    # add news
    for i in range(len(kbs_newslist)):
        news = get_kbsnews(kbs_newslist[i]['url'], session)
        kbs_newslist[i]['news'] = news

kbs_newslist


# In[34]:


def get_mbcnews(url, session):
    response = session.get(url)
    soup = BeautifulSoup(response.text, 'lxml')
    article_divs = soup.select_one("div.news_txt")
    text = article_divs.get_text(separator="\n", strip=True)
    pattern = r"\nMBC뉴스 [가-힣]+입니다\.[\s\S]*"
    cleaned_text = re.sub(pattern, "", text).strip()
    pattern1 = r"\nMBC 뉴스 [가-힣]+입니다\.[\s\S]*"
    cleaned_text = re.sub(pattern1, "", cleaned_text).strip()
    return cleaned_text


# In[110]:


def get_mbcnewslist(date, mbc_program_url, driver, session):
    # Get Selenium driver response of mbc news url
    driver.get(mbc_program_url)
    wait = WebDriverWait(driver, 15)
    wait.until(EC.presence_of_element_located((By.CLASS_NAME, "item")))

    # Get html elements containing label box-content
    mbc_source = driver.page_source
    soup = BeautifulSoup(mbc_source, 'lxml')
    mbc_news_html = soup.select("li.item")

    # get newslist, which contains title, and url of news. note that it is yet unsanitized.
    session = requests.Session()
    mbc_newslist = []
    for item in mbc_news_html:
        title = None
        if item.find('span', class_='tit ellipsis2'):
            title = item.find('span', class_='tit ellipsis2').get_text(strip=True)
        elif item.find('span', class_='tit ellipsis'):
            title = item.find('span', class_='tit ellipsis').get_text(strip=True)
        else:
            "N/A"
        if (title.startswith('[톱플레이]')):
            break
        link = item.find('a').get('href')
        news = get_mbcnews(link, session)
        mbc_newslist.append({'title': title, 'url': link, 'broadcast_date': date, 'news': news})

    for i in range(len(mbc_newslist)):
        mbc_newslist[i]['order'] = i + 1

    return mbc_newslist

mbc_newslist


# In[115]:


def get_sbsnews(url, session):
    response = session.get(url)
    soup = BeautifulSoup(response.text, 'lxml')

    script_tag = soup.find('script', type='application/ld+json')
    if script_tag:
        # Get the string content of the script tag
        json_text = script_tag.string

        # 4. Parse the JSON text into a Python dictionary
        data = json.loads(json_text)

        # 5. Access the "articleBody" value
        article_body = data.get("articleBody")

    return article_body


# In[116]:


def get_sbsnewslist(date, sbs_program_url, driver, session):
    # Get Selenium response of sbs url
    driver.get(sbs_program_url)
    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'li[itemprop="itemListElement"]')))

    sbs_source = driver.page_source
    soup = BeautifulSoup(sbs_source, 'lxml')
    sbs_news_html = soup.select('li[itemprop="itemListElement"]')

    sbs_base_url = "https://news.sbs.co.kr"
    sbs_newslist = []
    for item in sbs_news_html:
        category_tag = item.find("em", class_="cate")
        if category_tag and category_tag.get_text(strip=True) == "스포츠":
            continue
        title = item.find('img').get('alt')
        relative_link = item.find('a').get('href')
        full_link = urljoin(sbs_base_url, relative_link)
        news = get_sbsnews(full_link, session)

        if title.startswith('[날씨]'):
            break

        sbs_newslist.append({'title': title, 'url': full_link, 'broadcast_date': date, 'news': news})

    for i in range(len(sbs_newslist)):
        sbs_newslist[i]['order'] = i + 1   


    return sbs_newslist


# In[118]:


sbs_newslist = get_sbsnewslist(date, sbs_program_url, driver, session)
sbs_newslist

