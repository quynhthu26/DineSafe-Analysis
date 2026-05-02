import requests
import pandas as pd 
api_key = '7f274a0b09ee45498151ad24a7fd452e'
url = f"https://newsapi.org/v2/everything?q=artificial+intelligence&apiKey={api_key}"
response = requests.get(url).json() 

for article in response['articles']:
    print(article['title'])        # headline
    print(article['url'])          # link
    print(article['description'])  # summary
    print(article['publishedAt'])  # date
    print('---')    