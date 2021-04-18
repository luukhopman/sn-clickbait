import os
import re
import json
import pickle
import logging
import datetime
import requests
import tweepy as tp
import unidecode
from bs4 import BeautifulSoup

DEV = True
TEST_URL = 'https://www.soccernews.nl/news/797733/hierom-investeren-bedrijven-vijftig-miljoen-in-psv'
SAVE_FILE = 'saved_url'

logging.basicConfig(filename='bot.log',
                    format='%(asctime)s %(levelname)s:%(message)s',
                    datefmt=r'%Y-%m-%d %H:%M:%S',
                    level=logging.INFO)


class ClickbaitBot:
    '''
    Twitter bot that scrapes and parses clickbaited news articles
    '''

    def __init__(self, save_file, test_url=None):
        self.save_file = save_file
        self.test_url = test_url

    def get_twitter_api(self):
        auth = tp.OAuthHandler(os.environ['CONSUMER_KEY'],
                               os.environ['CONSUMER_SECRET'])
        auth.set_access_token(os.environ['ACCESS_TOKEN'],
                              os.environ['ACCESS_SECRET'])
        return tp.API(auth)

    def retrieve_article_url(self, username):
        '''
        Returns the last article url tweeted on Twitter account 
        '''
        last_tweet = self.get_twitter_api().user_timeline(username, count=1)[0]
        last_url = str(last_tweet.entities['urls'][0]['expanded_url'])
        article_url = unidecode.unidecode(last_url)
        return article_url

    def check_new_article_url(self, article_url):
        '''
        Returns True if the bot has not encountered the article
        '''
        file_exists = os.path.isfile(self.save_file)
        if file_exists:
            with open(self.save_file, 'rb') as f:
                saved_url = pickle.load(f)
        else:
            with open(self.save_file, 'wb') as f:
                pickle.dump(article_url, f)
            return True
        if article_url == saved_url:
            return False
        else:
            with open(self.save_file, 'wb') as f:
                pickle.dump(article_url, f)
            return True

    def scrape_article(self, url):
        '''
        Scrapes and returns the article title, preface, body and keywords
        '''
        try:
            page_tree = requests.get(
                url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:25.0)'})

            page_soup = BeautifulSoup(page_tree.content.decode(
                'utf-8', 'ignore'), 'html.parser')

            title = page_soup.find('h1', {'itemprop': 'headline'}).text
            preface = page_soup.find('p', attrs={'class': 'prelude'}).text
            keywords = page_soup.find(
                'meta', attrs={'name': 'keywords'})['content'].split(',')

            paragraphs = str(page_soup.findAll('p')[1])
            paragraphs = paragraphs.split('<blockquote')[0].split('<br/><br/>')
        except UnicodeDecodeError as e:
            raise UnicodeDecodeError('Problem with the article encountered')

        body = []
        for paragraph in paragraphs:
            paragraph = re.sub(re.compile('<.*?>'), '', paragraph)
            if paragraph is not None:
                body.append(paragraph)

        return title, preface, body, keywords

    def get_source_url(self, text):
        '''
        Attemps to find the article source and returns its url
        '''
        text = ''.join(text)
        websites = ['Algemeen Dagblad', 'Voetbal International',
                    'Telegraaf', 'Eindhovens Dagblad', 'Fox Sports']
        if not any(w in text for w in websites) or '"' not in text:
            return None

        quote = text.split('"')[1]

        try:
            if len(quote) > 25:
                quote = quote[:500]  # Use first 500 characters for search
                url = 'https://www.googleapis.com/customsearch/v1?key={}&cx={}&q={}'.format(
                    os.environ['API_KEY'], os.environ['SEARCH_ENGINE_ID'], quote)
                data = requests.get(url).json()
                search_items = data.get("items")

                if search_items:
                    link = search_items[0].get('link')
                    date = search_items[0].get('pagemap')['metatags'][0].get(
                        'article:published_time')[0:10]
                    timestamp = '{:%Y-%m-%d}'.format(datetime.datetime.now())
                    if date == timestamp:  # If published totday
                        return '\U0001f4dd {}'.format(link)
        except Exception as e:
            logging.error(e)
        return None

    def check_article(self, title, preface, body):
        '''
        Filters the articles based on several criteria
        '''
        text = ' '.join(body)
        article_length = len(preface) + len(text)
        if article_length < 400:
            logging.info(f'Article too short ({article_length} words)')
            return False
        if article_length > 2000:
            logging.info(f'Article too long ({article_length} words)')
            return False
        if 'greep uit de reacties' in text.lower():
            logging.info('Tweets')
            return False
        if 'scoreverloop' in text.lower():
            logging.info('Match report')
            return False
        if title.lower().startswith(('de 11', 'opstelling')):
            logging.info('Line-up')
            return False
        return True

    def create_tweet_text(self, title, keywords, text):
        '''
        Create the text that is tweeted by the bot
        '''
        with open('hashtags.json') as json_file:
            hashtag_dict = json.loads(json_file.read())

        keyword_list = []

        for keyword in keywords:
            if keyword in hashtag_dict:
                if keyword.casefold() in title.casefold() and len(keyword.split()) == 1:
                    title = title[:title.casefold().find(keyword.casefold(
                    ))] + '#' + title[title.casefold().find(keyword.casefold()):]
                else:
                    keyword_list.append('#' + hashtag_dict[keyword])
            elif not any(keyword in title for keyword in keyword.split()):
                keyword_list.append(keyword)

        if keyword_list:
            keywords = '(' + ', '.join(keyword_list) + ')'
        else:
            keywords = None

        if title[0] not in ["'", '"']:
            title = "'" + title + "'"

        source_url = self.get_source_url(text)

        tweet_text = '{}'.format(title)
        if source_url:
            tweet_text += '\n\n{}'.format(source_url)
        if keywords:
            tweet_text += '\n\n{}'.format(keywords)

        return tweet_text

    def parse_text(self, raw_text, font):
        '''Parse the article into text that can be drawn on image'''
        word_list = raw_text.split()

        word_list = [word + ' ' for word in word_list]

        words = 0
        width = 0
        for word in word_list:
            words += 1
            width += font.getsize(word)[0]
            if width > 950:
                word_list.insert(words - 1, '\n')
                width = 0

        if len(word_list) != 0 and word_list[-1] == '\n':
            del word_list[-1]

        parsed_text = ''.join(word_list)

        return parsed_text

    def get_sentences(self, text):
        '''Returns the number of sentences in text'''
        sentences = 1 + text.count('\n')
        return sentences

    def draw_image(self, title, preface, body):
        '''Creates and saves the articles in image format'''
        from PIL import ImageFont
        from PIL import Image
        from PIL import ImageDraw

        title_fnt = ImageFont.truetype('fonts/Roboto-Bold.ttf', 44)
        preface_fnt = ImageFont.truetype('fonts/Roboto-Medium.ttf', 38)
        body_fnt = ImageFont.truetype('fonts/Roboto-Regular.ttf', 34)

        title_parsed = self.parse_text(title, title_fnt)
        preface_parsed = self.parse_text(preface, preface_fnt)

        body_parsed = []
        for paragraph in body:
            parsed_paragraph = self.parse_text(paragraph, body_fnt)
            parsed_paragraph = parsed_paragraph.strip()
            body_parsed.append(parsed_paragraph + '\n')
        body_parsed = '\n'.join(body_parsed).strip()

        height_header = 30 + 50 * self.get_sentences(title_parsed)
        height_preface = height_header + 15
        height_body = 10 + height_preface + \
            self.get_sentences(preface_parsed) * 36
        height_image = 85 + height_body + self.get_sentences(body_parsed) * 36

        img = Image.new('RGB', (1000, height_image), color=(5, 5, 5))

        d = ImageDraw.Draw(img)

        d.rectangle((0, 0, 1000, height_header),  fill=(15, 140, 85))

        d.text((30, 16), title_parsed, font=title_fnt)
        d.text((30, height_preface), preface_parsed, font=preface_fnt)
        d.text((30, height_body + 45), body_parsed, font=body_fnt)

        img.save('out.png')

    def tweet_image(self, tweet_text):
        '''Tweets the tweet text and image'''
        if DEV == False:
            self.get_twitter_api().update_with_media('out.png', tweet_text)
            logging.info('Posted new image')
        else:
            tweet_text = tweet_text.replace('\U0001f4dd ', '')
            logging.info(f"[DEV] {tweet_text}")

    def main(self):
        if self.test_url:
            article_url = self.test_url
            new_article = True
        else:
            article_url = self.retrieve_article_url('Soccernews_nl')
            new_article = self.check_new_article_url(article_url)

        if new_article or DEV:
            title, preface, body, keywords = self.scrape_article(article_url)
            accepted_article = self.check_article(title, preface, body)
            if accepted_article:
                tweet_text = self.create_tweet_text(title, keywords, body)
                self.draw_image(title, preface, body)
                self.tweet_image(tweet_text)
        else:
            logging.info('No new article')
        return new_article


if __name__ == '__main__':
    clickbait_bot = ClickbaitBot(save_file=SAVE_FILE, test_url=TEST_URL)
    clickbait_bot.main()
