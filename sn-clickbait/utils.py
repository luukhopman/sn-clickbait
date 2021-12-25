import os
import tweepy as tp


def get_twitter_api():
    auth = tp.OAuthHandler(os.environ['CONSUMER_KEY'],
                           os.environ['CONSUMER_SECRET'])
    auth.set_access_token(os.environ['ACCESS_TOKEN'],
                          os.environ['ACCESS_SECRET'])
    return tp.API(auth)
