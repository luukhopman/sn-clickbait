import json
import os
import pickle
import re

import requests
import unidecode
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont

from .logger import logger
from .utils import get_twitter_api

CUSTOM_URL = None


class Article:
    """
    Scrapes the last tweeted article from the website.
    """

    USERNAME = 'Soccernews_nl'
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
            self.soup = self.get_article_soup()
            self.title = self.parse_title()
            self.content = self.parse_content()
            self.text = ' '.join(self.content)
            self.preface = self.content.pop(0)
            self.is_valid = self.check_article()
            self.source_url = self.get_source_url()

    def retrieve_url(self):
        """
        Returns the last article url tweeted on Twitter account.
        """
        last_tweet = self.api.user_timeline(self.USERNAME, count=1)[0]
        url = last_tweet.entities['urls'][0]['expanded_url']
        # Transliterate an Unicode object into an ASCII string
        url = unidecode.unidecode(url)
        logger.debug(url)
        return url

    def check_new_url(self):
        """
        Returns True is the bot has not encountered the article before.
        Writes url of last article to pickle.
        """
        file_exists = os.path.isfile(self.SAVE_FILE)

        # Create pickle file if it does not exist
        if not file_exists:
            with open(self.SAVE_FILE, 'wb') as f:
                pickle.dump(self.url, f)
            return True

        # Read pickle file
        with open(self.SAVE_FILE, 'rb') as f:
            saved_url = pickle.load(f)

        # Check if article was already encountered
        if self.url == saved_url:
            logger.debug('No new article.')
            return False

        with open(self.SAVE_FILE, 'wb') as f:
            pickle.dump(self.url, f)
        return True

    def get_article_soup(self):
        """
        Requests the url and returns the parsed page soup.
        """
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:25.0)'}
            page_tree = requests.get(self.url, headers=headers)
            soup = BeautifulSoup(page_tree.content.decode(
                'utf-8', errors='ignore'), 'html.parser')
            return soup
        except UnicodeDecodeError as e:
            raise UnicodeDecodeError('Problem with the article encountered', e)

    def parse_title(self):
        """
        Parses the title from the article.
        """
        return self.soup.find('h1', {'class': 'entry-title'}).text

    def parse_content(self):
        """
        Parses the content text from the article
        """
        content = self.soup.find('div', attrs={'class': 'entry-content'})
        paragraphs = [p.text for p in content.find_all('p')]

        content = []
        for paragraph in paragraphs:
            # Ignore ads (links outside website)
            if 'target="_blank"' in paragraph:
                continue
            # Remove HTML tags
            paragraph = re.sub(re.compile('<.*?>'), '', paragraph).strip()
            if paragraph:
                content.append(paragraph)
        return content

    def parse_keywords(self):
        """
        Parses the keywords from the article metadata
         """
        return self.soup.find('meta', attrs={'name': 'keywords'})['content'].split(',')

    def check_article(self):
        """
        Filters the articles based on several criteria.
        """
        article_length = len(self.preface) + len(self.text)
        if article_length < 400:
            logger.debug('Article too short ({} words)'.format(article_length))
            return False
        if article_length > 2000:
            logger.debug('Article too long ({} words)'.format(article_length))
            return False
        if 'twitter' in self.title.lower() or 'greep uit de reacties' in self.text.lower():
            logger.debug('Tweets')
            return False
        if self.title.lower().startswith(('de 11', 'opstelling')):
            logger.debug('Line-up')
            return False
        return True

    def get_source_url(self):
        """
        Attemps to find the article source and returns its url.
        Alternatively, it returns the Twitter handle of the journalist or source.
        """
        journalists = {'Rik Elfrink': '@RikElfrink',
                       'Mike Verweij': '@MikeVerweij',
                       'Krabbendam': '@Mkrabby',
                       'Fabrizio Romano': '@FabrizioRomano'}

        journalists_found = [w for w in journalists if w in ' '.join(
            [self.title, self.preface, self.text])]

        if journalists_found:
            return journalists[journalists_found[0]]  # Twitter handle

        sources = {'Algemeen Dagblad': '@ADnl',
                   'Voetbal International': '@VI_nl',
                   'Telegraaf': '@telegraaf',
                   'Eindhovens Dagblad': '@ED_Regio',
                   'ESPN': '@ESPNnl',
                   'Parool': '@parool',
                   'RTV Rijnmond': '@RTV_Rijnmond',
                   'De Gelderlander': '@DeGelderlander',
                   'NOS': '@NOSsport',
                   'NU.nl': 'NUnl',
                   'NRC': '@nrc'}

        sources_found = [w for w in sources if w in ' '.join(
            [self.title, self.preface, self.text])]

        if not sources_found:
            return None

        quotes = re.findall(r'"([^"]+)"', self.text)
        if not quotes:
            return None

        for quote in quotes:
            quote_words = quote.split()[:32]  # Use first 32 words for search
            if len(quote_words) < 10:  # Too short to be meaningful
                continue
            quote = '"' + ' '.join(quote_words) + '"'
            base_url = 'https://www.googleapis.com/customsearch/v1?key={}&cx={}&q={}'
            url = base_url.format(os.environ['API_KEY'],
                                  os.environ['SEARCH_ENGINE_ID'],
                                  quote)
            data = requests.get(url).json()
            search_items = data.get('items')
            if search_items:
                source_link = search_items[0].get('link')
                logger.debug(source_link)
                return source_link
        return sources[sources_found[0]]  # Twitter handle


class TextImage:
    """
    Turns scraped article into an image.
    """

    IMG_WIDTH = 1100

    TITLE_FONT = ImageFont.truetype('fonts/Roboto-Bold.ttf', 44)
    PREFACE_FONT = ImageFont.truetype('fonts/Roboto-Medium.ttf', 38)
    content_FONT = ImageFont.truetype('fonts/Roboto-Regular.ttf', 34)

    BG_COLOR = (5, 5, 5)
    HIGHLIGHT_COLOR = (15, 140, 85)

    SIDE_PAD = 25
    TITLE_PAD = 16
    PREFACE_PAD = 32
    content_PAD = 32

    OUT_PATH = 'img.png'

    def __init__(self, article):
        self.title = article.title
        self.preface = article.preface
        self.content = article.content

        self.title_parsed = self.parse_text(self.title, self.TITLE_FONT)
        self.preface_parsed = self.parse_text(self.preface, self.PREFACE_FONT)

        content_parsed = []
        for paragraph in self.content:
            parsed_paragraph = self.parse_text(paragraph, self.content_FONT)
            content_parsed.append(parsed_paragraph)
        self.content_parsed = '\n\n'.join(content_parsed)

        self.title_height = TextImage.get_text_height(self.title_parsed,
                                                      self.TITLE_FONT)
        self.preface_height = TextImage.get_text_height(self.preface_parsed,
                                                        self.PREFACE_FONT)
        self.content_height = TextImage.get_text_height(self.content_parsed,
                                                        self.content_FONT)

        self.path = self.draw_image()

    def parse_text(self, text, font):
        """
        Splits text into fixed-width parts.
        """
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
        """
        Determine text height using a scratch image.
        """
        img = Image.new('RGBA', (1, 1))
        d = ImageDraw.Draw(img)
        height = d.textsize(text, font)[1]
        return height

    def draw_image(self):
        """
        Creates the articles in image format. Saves image as PNG.
        """
        y_title = self.TITLE_PAD
        y_preface = y_title + self.title_height + self.PREFACE_PAD
        y_content = y_preface + self.preface_height + self.content_PAD

        img_height = y_content + self.content_height + self.content_PAD
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

        # Draw content
        d.text(xy=(self.SIDE_PAD, y_content),
               text=self.content_parsed,
               font=self.content_FONT)

        img.save(self.OUT_PATH)
        return self.OUT_PATH


class Tweet:
    """
    Creates and sends the tweet containing the articles image.
    """

    def __init__(self, api, article, image):
        self.api = api
        self.title = article.title
        self.preface = article.preface
        self.source_url = article.source_url
        self.tweet = self.create_tweet()
        self.img = image.path

    def create_tweet(self):
        """
        Create the text that is tweeted by the bot.
        """
        tweet = self.title

        # Put title in between quotes if it's not already
        if not tweet.startswith(("'", '"', '‘')) or not tweet.endswith(("'", '"', '’')):
            tweet = "'" + tweet + "'"

        # Add hashtags
        with open('hashtags.json', encoding='utf-8') as json_file:
            hashtag_dict = json.loads(json_file.read())

        hashtags = []
        for keyword, hashtag in hashtag_dict.items():
            keyword_idx = tweet.casefold().find(keyword.casefold())
            if len(keyword.split()) == 1 and keyword_idx != -1:
                # Add the hashtag in the tweet text
                tweet = tweet[:keyword_idx] + '#' + tweet[keyword_idx:]
            elif keyword in self.preface:
                # Display the hashtag below the tweet text
                hashtags.append(hashtag)

        if self.source_url:
            tweet += '\n\n\U0001f4dd {}'.format(self.source_url)

        if hashtags:
            hashtags_tweet = '(' + ', '.join(hashtags) + ')'
            tweet += '\n\n{}'.format(hashtags_tweet)

        return tweet

    def send_tweet(self):
        """
        Tweets the tweet text and image
        """
        self.api.update_with_media(self.img, self.tweet)
        logger.debug('Posted new image')


def main():
    """
    Main loop of the bot.
    """
    api = get_twitter_api()
    article = Article(api, CUSTOM_URL)
    if article.new_article and article.is_valid:
        image = TextImage(article)
        tweet = Tweet(api, article, image)
        if CUSTOM_URL:
            print(tweet.tweet)
        else:
            tweet.send_tweet()


if __name__ == '__main__':
    main()
