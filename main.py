import asyncio
import requests
from bs4 import BeautifulSoup
import pandas as pd
import string
import aiohttp
import datetime
import re
from apikey import apikey

#Get user input
search_string = input("Enter the job title/department you are looking to target: ")
location_string = input("Enter the location that you are looking to target: ")
salary_string = input("Enter the salary that you want the jobs to be above: ")

#Global Variables
html = ''
num_pages = 0
urls = []
count = 0
columns = ["company","job_title", "link", "salary", "posted_date"]
df = pd.DataFrame(columns=columns)
# The semaphore limits the number of async calls that we can make at once, based on whatever you are
# limited by. In this case, the API that we are calling only allows for 10 concurrent calls,
# thus the semaphore is set to 10. If you had a more robust pricing tier you would change the semaphore.
semaphore = asyncio.Semaphore(10)

#Transforms user inputs into strings into text for URLs
def format_search_and_location(s):
    words = s.split()
    words = [word.capitalize() for word in words]
    final_string = "+".join(words)
    return final_string

def format_salary(s):
        # Define a string of punctuation characters
        punctuation = string.punctuation
        # Remove all punctuation characters from the input string
        s = ''.join(char for char in s if char not in punctuation)
        # Remove all non-numeric characters from the input string
        s = ''.join(char for char in s if char.isnumeric())
        return s


location = format_search_and_location(location_string)
search = format_search_and_location(search_string)
salary = format_salary(salary_string)

#This function gets the first page of the results in order to
#get number of pages and total number of expected jobs
async def get_page():
    global location
    global search
    url = 'https://api.webscraping.ai/html'
    api_key = apikey
    target_url = f'https://www.indeed.com/jobs?q={search}+%24{salary}&l={location}&filter=0'
    proxy = 'residential'

    params = {
        'api_key': api_key,
        'url': target_url,
        'proxy': proxy,
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        global html
        html = response.text
        soup = BeautifulSoup(html, 'lxml')
        page_div = soup.find('div', attrs={'class': 'jobsearch-JobCountAndSortPane-jobCount'})
        if page_div.find('span').text == None:
            print(f"Error scraping first page: {e}")
            print("Hold on, trying again...")
            await asyncio.sleep(5)
            await get_page()
        else:
            stringy = page_div.find('span').text
            first_word = stringy.split()[0].translate(str.maketrans("", "", string.punctuation))
            global num_pages
            num_pages = int((int(first_word) / 15)) + 1
            if num_pages > 66:
                num_pages = 66
                first_word = 990
            print(f"There are {first_word} jobs over {num_pages} pages for your search terms and location.")
    except requests.exceptions.HTTPError as e:
        print(f"Error scraping first page: {e}")
        print("Hold on, trying again...")
        await asyncio.sleep(5)
        await get_page()

#This function uses the number of pages to create an array of every URL we will be calling.
#This is necessary because in order for us to call all of the pages async, we need an
# array of everything we will be calling
def make_url_list(num_pages, count):
    global location
    global search
    for pages in range(num_pages):
        url = f'https://www.indeed.com/jobs?q={search}+%24{salary}&l={location}&start={count}'
        global urls
        urls.append(url)
        count += 10

#This function will be called in the get_tasks() function to get the entire html
#of each page that we are requesting
async def fetch_page(session, url, params, address, i, links):
    #See note under global variables for understanding of the semaphore
    async with semaphore:
        try:
            async with session.get(url, params=params, ssl=False) as response:
                html1 = await response.text()
                #Here, instead of just getting all of the HTML I added in some error handling, as
                #sometimes the HTML returned can be unpredictable. Sometimes the javascript doesnt render
                #completely, sometimes the javascript doesnt render at all, there are many mistakes than can
                #occur when trying to obtain a pages HTML. I started by only doing error handling in the
                #add_to_posts() function, but found that if I nip issues in the bud here it makes parsing
                #through the HTML easier later.
                soup = BeautifulSoup(html1, 'lxml')
                outer_most_point = soup.find('div', attrs={'class': 'mosaic-provider-jobcards'})
                if outer_most_point is None:
                    print("Page didn't load right, trying again..")
                    return await fetch_page(session, url, params, address, i, links)
                else:
                    print(f"Added page {i + 1} of {len(links)} to pages.")
                    return html1
        #python has a tendency to break if something isnt planned for, so I learned some error
        #handling for this section. Everything is accounted for and if there is an error it simply
        #will retry the same function to make sure it got the HTML for that page.
        except aiohttp.ClientResponseError as e:
            print(f"Error scraping page {i+1} of {len(links)}: {e}")
            await asyncio.sleep(5)
            return await fetch_page(session, url, params, address, i, links)
        #Exception is a catch all in python for any other errors that I may have not thought of
        #or encountered. It also will retry the same function to make sure it got the HTML for that page.
        except Exception as e:
            print(f"Unexpected error scraping page {i+1} of {len(links)}: {e}")
            return await fetch_page(session, url, params, address, i, links)

#this function creates an array of tasks, which is essentially an array of functions that will make the call
#to an api to get the page HTML. This is necessary so we can send them all at once.
def get_tasks(session, links):
    tasks = []
    for i, address in enumerate(links):
        url = 'https://api.webscraping.ai/html'
        api_key = apikey
        target_url = address
        proxy = 'residential'

        params = {
            'api_key': api_key,
            'url': target_url,
            'proxy': proxy,
        }
        tasks.append(fetch_page(session, url, params, address, i, links))
    return tasks

#this short function is the meat and potatoes of this program. It will async call the entire array of tasks
#Of course, 10 at a time because of the semaphore. It will then populate each page into the pages array
#for us to parse through later
async def get_all_pages(links):
    async with aiohttp.ClientSession() as session:
        tasks = get_tasks(session, links)
        pages = await asyncio.gather(*tasks, return_exceptions=True)
        return [page for page in pages if page is not None]

#This was BY FAR the most annoying portion of this project. With the javascript rendering sometimes with a delay,
#sometimes partially, sometimes not at all, this section needs to be called more than once if it will comepletely
#miss an entire page of Company Names. You can see in all of the sections I will write the HTML to a .txt file
#so that I can manually go through issues and find other ways to get the same data if the javascript rendered
#differently
def add_to_posts(pages):
    global df
    lists = []
    for index, page in enumerate(pages):
        soup = BeautifulSoup(page, 'lxml')
        results = soup.find('ul', attrs={'class': 'jobsearch-ResultsList'})
        lists += results.find_all('div', attrs='job_seen_beacon')
        print("going through a page")
    for item in lists:
        # Extract company
        company_element = item.find("span", class_="companyName")
        if company_element is not None:
            company = company_element.text
        elif company_element is None:
            company_info_div = item.find("div", class_="companyInfo")
            company_element = company_info_div.find("span")#,{"class": lambda x: x and x.startswith("css")})
            if company_element is None:
                company = 'No Company Name'
                # with open(f'no company object{index}.txt', 'w') as f:
                #     f.write(str(item))
            else:
                company = company_element.text
                # with open(f'no company object{index}.txt', 'w') as f:
                #     f.write(str(item))
        else:
            company = 'No Company Name'
            # with open(f'no company object.txt{index}', 'w') as f:
            #     f.write(str(item))
        # Extract job title
        job_element = item.find("span", {"id": lambda x: x and x.startswith("jobTitle")})
        if job_element is not None:
            job_title = job_element.text
        else:
            job_title = "No Job Title"
            # with open('no job title object.txt', 'w') as f:
            #     f.write(str(item))
        # Extract link
        link_element = item.find("a", class_="jcs-JobTitle")["href"]
        if link_element is not None:
            link = link_element
        else:
            link = "no link found"
            # with open('no link object.txt', 'w') as f:
            #     f.write(str(item))
        # Extract salary
        sal_element = item.find("div", class_="attribute_snippet")
        if sal_element is not None:
            salary = item.find("div", class_="attribute_snippet").text.strip()
        else:
            salary = 'No Salary Listed'
            # with open('no salary object.txt', 'w') as f:
            #     f.write(str(item))
        if item.find('span', attrs={'class': 'date'}) != None:
            post_date = item.find('span', attrs={'class': 'date'}).text
        else:
            post_date = 'No Post Date'
            # with open('no date object.txt', 'w') as f:
            #     f.write(str(item))
        job = {
            "company": company,
            "job_title": job_title,
            "link": f"http://indeed.com{link}",
            "salary": salary,
            "posted_date": post_date
        }
        df = df._append(job, ignore_index=True)

#So the "post_date" section of the dataframe, actually holds a string from the HTML we parsed through that
#says something like "posted 12 days ago" or "employer active 3 days ago". So this function transforms those
#strings into accurate dates based on the date that you are pulling the data on. Clever idea from Mr.Fugu's
#datascience youtube channel, and from his github. His channel has helped me greatly.
def date_transform():
    global df
    dates_converted = []
    for i in df['posted_date']:
        if re.findall(r'[0-9]', i):
            # if the string has digits convert each entry to single string: ['3','0']->'30'
            b = ''.join(re.findall(r'[0-9]', i))
            # convert string int to int and subtract from today's date and format
            g = (datetime.datetime.today() - datetime.timedelta(int(b))).strftime('%m-%d-%Y')
            dates_converted.append(g)
        else:  # this will contain strings like: 'just posted' or 'today' etc before convert
            dates_converted.append(datetime.datetime.today().strftime('%m-%d-%Y'))
    df['posted_date'] = dates_converted

#Goes through the whole thing. The whole shabang. This took me a week to make and holy shit i am so proud.
def main():
    print("Lets find you some leads!")
    asyncio.run(get_page())
    make_url_list(num_pages, count)
    pages = asyncio.run(get_all_pages(urls))
    #debugging
    # with open('pages.json', 'w') as f:
    #     json.dump(pages, f)
    add_to_posts(pages)
    date_transform()
    num_rows = df['company'].count()
    print(f"{num_rows} jobs scraped..")
    df.to_csv(f'{search_string}_leads_from_{location_string}_above_{salary}.csv', index=False)
    print("We just made magic happen. Leads exported to .csv!")

#Calls main function
if __name__ == "__main__":
    main()


