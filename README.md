# Indeed-Scraper

Hello! This was a fun project I used to automate some parts of my sales job. This web scraper uses webscraping.ai as an api that renders the HTML for a given website. 

In order to use it the way I do, you would run the main.py file (you need to input your webscraping.ai apikey) and that will output you a .csv file with each job, the link to that job, the date it was posted, and the company it is for. This raw data can be useful for some, however for an end user it can be organized more neatly than this. 

Using the .ipynb you can use the first cell of the notebook to combine several .csv files from several times that you ran the main.py script.

You can use the second cell of the jupyter notebook to organize the job listings by company, with a count of how many listings each company has and also the date that they last posted a job listing. 

The thought behind this transformation is that you can assume a company with more jobs listed for a certain department/title have more budget for that department, and how recently they posted a job is how early you are to the party. 
