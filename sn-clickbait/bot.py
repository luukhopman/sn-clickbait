import os
import re
import json
import pickle
import datetime
import requests
import unidecode
from bs4 import BeautifulSoup
from PIL import ImageFont
from PIL import Image
from PIL import ImageDraw
from .logger import logger
from .utils import get_twitter_api


class Article:
    """
    Scrapes the last tweeted article from the website.
    """

    USERNAME = 'soccernews_nl'
    SAVE_FILE = 'saved_url'

    def __init__(self, api, url=None):
        self.api = api
        if url:
            self.url = url
            self.new_article = True
        else:
            self.url = self.retrieve_url()
            self.new_article = self.check_new_url()

        if self.new_article:
            self.soup = self.scrape_article()
            self.title = self.parce_title()
            self.preface = self.parse_preface()
            self.keywords = self.parse_keywords()
            self.body = self.parse_body()
            self.is_valid = self.check_article()
            self.source_url = self.get_source_url()

    def retrieve_url(self):
        """Returns the last article url tweeted on Twitter account."""
        last_tweet = self.api.user_timeline(self.USERNAME, count=1)[0]
        url = last_tweet.entities['urls'][0]['expanded_url']
        url = unidecode.unidecode(url)
        logger.debug(url)
        return url

    def check_new_url(self):
        """Returns True is the bot has not encountered the article before."""
        file_exists = os.path.isfile(self.SAVE_FILE)
        if not file_exists:
            with open(self.SAVE_FILE, 'wb') as f:
                pickle.dump(self.url, f)
            return True
        else:
            with open(self.SAVE_FILE, 'rb') as f:
                saved_url = pickle.load(f)
            if self.url == saved_url:
                logger.debug('No new article.')
                return False
            else:
                with open(self.SAVE_FILE, 'wb') as f:
                    pickle.dump(self.url, f)
                return True

    def scrape_article(self):
        """Scrapes and returns the article title, preface, body and keywords"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:25.0)'}
            page_tree = requests.get(self.url, headers=headers)
            soup = BeautifulSoup(page_tree.content.decode(
                'utf-8', errors='ignore'), 'html.parser')
            return soup
        except UnicodeDecodeError as e:
            raise UnicodeDecodeError('Problem with the article encountered', e)

    def parce_title(self):
        """Parses the title from the article."""
        return self.soup.find('h1', {'itemprop': 'headline'}).text

    def parse_preface(self):
        """Parses the preface from the article."""
        return self.soup.find('p', attrs={'class': 'prelude'}).text

    def parse_body(self):
        """Parses the body text from the article"""
        paragraphs = str(self.soup.findAll('p')[1])
        paragraphs = paragraphs.split('<blockquote')[0].split('</p><p>')

        body = []
        for paragraph in paragraphs:
            if 'bet365' in paragraph:  # Ignore betting ads
                continue
            paragraph = re.sub(re.compile('<.*?>'), '',
                               paragraph)  # Remove HTML tags
            if paragraph:
                body.append(paragraph)
        return body

    def parse_keywords(self):
        """Parses the keywords from the article metadata"""
        return self.soup.find('meta', attrs={'name': 'keywords'})['content'].split(',')

    def check_article(self):
        """Filters the articles based on several criteria."""
        text = ' '.join(self.body)
        article_length = len(self.preface) + len(text)
        if article_length < 400:
            logger.debug(
                'Check: Article too short ({} words)'.format(article_length))
            return False
        if article_length > 2000:
            logger.debug(
                'Check: Article too long ({} words)'.format(article_length))
            return False
        if 'twitter' in self.title.lower():
            logger.debug('Check: Tweets')
            return False
        if self.title.lower().startswith(('de 11', 'opstelling')):
            logger.debug('Check: Line-up')
            return False
        return True

    def get_source_url(self):
        """Attemps to find the article source and returns its url."""
        text = ' '.join(self.body)
        sources = ['Algemeen Dagblad', 'Voetbal International',
                   'Telegraaf', 'Eindhovens Dagblad', 'Fox Sports']
        if not any(w in text for w in sources) or '"' not in text:
            return None

        quote = text.split('"')[1]

        if len(quote) < 20:  # Too short to be meaningful
            return None

        try:
            quote = quote[:250]  # Use first 250 characters for search
            url = 'https://www.googleapis.com/customsearch/v1?key={}&cx={}&q={}'.format(
                os.environ['API_KEY'], os.environ['SEARCH_ENGINE_ID'], quote)
            data = requests.get(url).json()
            search_items = data.get('items')

            if search_items:
                source_link = search_items[0].get('link')
                date = search_items[0].get('pagemap')['metatags'][0].get(
                    'article:published_time')[0:10]
                timestamp = '{:%Y-%m-%d}'.format(datetime.datetime.now())
                if date == timestamp:  # Published today
                    logger.debug(source_link)
                    return source_link
        except Exception as e:
            logger.error(e)
        return None


class TextImage:
    """
    Turns scraped article into an image.
    """

    IMG_WIDTH = 1000

    TITLE_FONT = ImageFont.truetype('fonts/Roboto-Bold.ttf', 44)
    PREFACE_FONT = ImageFont.truetype('fonts/Roboto-Medium.ttf', 38)
    BODY_FONT = ImageFont.truetype('fonts/Roboto-Regular.ttf', 34)

    BG_COLOR = (5, 5, 5)
    HIGHLIGHT_COLOR = (15, 140, 85)

    SIDE_PAD = 25
    TITLE_PAD = 16
    PREFACE_PAD = 32
    BODY_PAD = 48

    OUT_PATH = 'img.png'

    def __init__(self, title, preface, body):
        self.title = title
        self.preface = preface
        self.body = body

        self.title_parsed = self.parse_text(self.title, self.TITLE_FONT)
        self.preface_parsed = self.parse_text(self.preface, self.PREFACE_FONT)

        body_parsed = []
        for paragraph in body:
            parsed_paragraph = self.parse_text(paragraph, self.BODY_FONT)
            body_parsed.append(parsed_paragraph)
        self.body_parsed = '\n\n'.join(body_parsed)

        self.title_height = TextImage.get_text_height(self.title_parsed,
                                                      self.TITLE_FONT)
        self.preface_height = TextImage.get_text_height(self.preface_parsed,
                                                        self.PREFACE_FONT)
        self.body_height = TextImage.get_text_height(self.body_parsed,
                                                     self.BODY_FONT)

        self.path = self.draw_image()

    def parse_text(self, text, font):
        """Splits text into fixed-width parts."""
        word_list = [word + ' ' for word in text.split()]

        word_idx = 0
        sentence_width = 0
        max_width = self.IMG_WIDTH - (self.SIDE_PAD*2)
        for word in word_list:
            word_idx += 1
            sentence_width += font.getsize(word)[0]
            if sentence_width > max_width:
                word_list.insert(word_idx-1, '\n')
                sentence_width = 0

        parsed_text = ''.join(word_list).strip()

        return parsed_text

    @staticmethod
    def get_text_height(text, font):
        """Determine text height using a scratch image."""
        img = Image.new('RGBA', (1, 1))
        d = ImageDraw.Draw(img)
        height = d.textsize(text, font)[1]
        return height

    def draw_image(self):
        """Creates the articles in image format. Saves image as PNG."""
        y_title = self.TITLE_PAD
        y_preface = y_title + self.title_height + self.PREFACE_PAD
        y_body = y_preface + self.preface_height + self.BODY_PAD

        img_height = y_body + self.body_height + self.BODY_PAD
        img = Image.new('RGBA',
                        size=(self.IMG_WIDTH, img_height),
                        color=self.BG_COLOR)

        d = ImageDraw.Draw(img)

        # Draw title rectangle
        d.rectangle(xy=(0, 0, self.IMG_WIDTH, y_preface-self.TITLE_PAD),
                    fill=self.HIGHLIGHT_COLOR)

        # Draw title
        d.text(xy=(self.SIDE_PAD, y_title),
               text=self.title_parsed,
               font=self.TITLE_FONT)

        # Draw preface
        d.text(xy=(self.SIDE_PAD, y_preface),
               text=self.preface_parsed,
               font=self.PREFACE_FONT)

        # Draw body
        d.text(xy=(self.SIDE_PAD, y_body),
               text=self.body_parsed,
               font=self.BODY_FONT)

        img.save(self.OUT_PATH)
        return self.OUT_PATH


class Tweet:
    """
    Creates and sends the tweet containing the articles image.
    """

    def __init__(self, api, title, keywords, source_url, img):
        self.api = api
        self.title = title
        self.keywords = keywords
        self.source_url = source_url
        self.tweet = self.create_tweet()
        self.img = img

    def create_tweet(self):
        """Create the text that is tweeted by the bot"""
        tweet = self.title
        if not tweet.startswith(("'", '"')):
            tweet = "'" + tweet + "'"

        with open('hashtags.json') as json_file:
            hashtag_dict = json.loads(json_file.read())

        keyword_list = []
        for keyword in self.keywords:
            if keyword in hashtag_dict:
                keyword_idx = tweet.casefold().find(keyword.casefold())
                if len(tweet.split()) == 1 and keyword_idx != -1:
                    tweet = tweet[:keyword_idx] + '#' + tweet[keyword_idx:]
                else:
                    keyword_list.append('#' + hashtag_dict[keyword])
            elif not any(keyword in tweet for keyword in keyword.split()):
                keyword_list.append(keyword)

        if self.source_url:
            tweet += '\n\n\U0001f4dd {}'.format(self.source_url)

        if keyword_list:
            keywords = '(' + ', '.join(keyword_list) + ')'
            tweet += '\n\n{}'.format(keywords)

        return tweet

    def send_tweet(self):
        """Tweets the tweet text and image"""
        self.api.update_with_media(self.img, self.tweet)
        logger.debug('Posted new image')


if __name__ == '__main__':
    api = get_twitter_api()
    article = Article(api)
    if article.new_article:
        image = TextImage(article.title, article.preface, article.body)
        tweet = Tweet(api, article.title, article.keywords,
                      article.source_url, image.path)
        tweet.send_tweet()