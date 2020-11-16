import urllib.request
from html.parser import HTMLParser
import schedule
import time
import pandas as pd
import numpy as np
import psycopg2
import os

class MyHTMLParser(HTMLParser):
    before=''
    found=False
    filename=''
    def handle_starttag(self, tag, attrs):
        if tag == 'pre':
            if self.before == 'pre':
                self.found = True
        self.before = tag
    def handle_data(self, data):
        if self.found:
            self.filename = time.strftime("%Y%m%d-%H%M%S") + '.txt'
            with open(self.filename, 'a') as the_file:
                the_file.write(data)
            self.found=False

def downloadFile():
    fid=urllib.request.urlopen('http://wxstns.net/ALTA.html?fbclid=IwAR3ARyLXzVMGt7CHoDVVcVhcR-JgeAWfGbUPb0zwhDNpZqelCKt9jrCCJ0o')
    webpage=fid.read().decode('utf-8',errors='ignore')

    parser = MyHTMLParser()
    parser.feed(webpage)

    return parser.filename

def preprocessData(filename):
    df = pd.read_csv(
        filename,
        delim_whitespace=True,
        skiprows=5,
        header=None
    )

    df.dropna(axis=1, how='all')
    headers=['DATE','TIME','h2o_9664_1HR','Snow_9664_12HR','Temp_F°_8550_AVG','Temp_F°_10500_AVG','Temp_F°_11068_AVG','RH_8550_AVG','RH_10500_AVG','RH_11068_AVG','W_Spd_8550_AVG','W_Dir_8550_AVG','W_Gust_8550_MAX','W_Spd_10500_AVG','W_Dir_10500_AVG','W_Gust_10500_MAX','W_Spd_11068_AVG','W_Dir_11068_AVG','W_Gust_11068_MAX','h2o_8550_1HR']
    df.columns=headers

    return df
    #print(df)

def single_insert(conn, insert_req):
    """ Execute a single INSERT request """
    cursor = conn.cursor()
    try:
        cursor.execute(insert_req)
        conn.commit()
    except (Exception, psycopg2.DatabaseError) as error:
        print("Error: %s" % error)
        conn.rollback()
        cursor.close()
        return 1
    cursor.close()

def updateDB(db, df):
    DATABASE_URL = os.environ['DATABASE_URL']

    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    cursor=conn.cursor()

    cols = "\",\"".join([str(i).lower() for i in df.columns.tolist()])
    cols = "\"" + cols + "\""
    for i,row in df.iterrows():
        sql = "INSERT INTO " + db + " (" +cols + ") VALUES (" + "%s,"*(len(row)-1) + "%s)" 
        cursor.execute(sql, tuple(row))
        conn.commit()
    conn.close()

def createTable():
    DATABASE_URL = os.environ['DATABASE_URL']
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')

    # query = """
    #     CREATE TABLE whole_day_data (
    #         DATE              text,
    #         TIME              text,
    #         h2o_9664_1HR    float8,
    #         Snow_9664_12HR    float8,
    #         Temp_F°_8550_AVG  int4, 
    #         Temp_F°_10500_AVG int4,
    #         Temp_F°_11068_AVG int4,
    #         RH_8550_AVG      int4,
    #         RH_10500_AVG     int4,
    #         RH_11068_AVG     int4,
    #         W_Spd_8550_AVG    int4,
    #         W_Dir_8550_AVG    int4,
    #         W_Gust_8550_MAX   int4,
    #         W_Spd_10500_AVG   int4,
    #         W_Dir_10500_AVG   int4,
    #         W_Gust_10500_MAX  int4,
    #         W_Spd_11068_AVG   int4,
    #         W_Dir_11068_AVG   int4,
    #         W_Gust_11068_MAX  int4,
    #         h2o_8550_1HR    float8
    #     );"""   

    query = """
        CREATE TABLE daily_data (
            DATE                        text, 
            SNOWFALL                    float8, 
            PERIOD_OF_HEAVY_SNOWFALL    int4,
            WET_SNOW                    int4, 
            HEAVY_WIND_8550             int4,
            HEAVY_WIND_10500            int4,    
            HEAVY_WIND_11068            int4
        );"""
    single_insert(conn, query)

def inTomm(inch):
    return inch * 25.4

def inTocm(inch):
    return inch * 2.54

def calcSnowDensity(dfRow):
    if dfRow['Snowfall'] <= 0:
        return 0
    return inTomm(dfRow['h2o_9664_1HR']) / inTocm(dfRow['Snowfall']) * 100 * (1/1000) 

def analyzeData(df):
    df['Snowfall'] = df['Snow_9664_12HR'].diff()*-1
    snowfall = round(df['Snowfall'].agg(lambda x: x[x>0].sum()), 3)

    heavysnowfallDf = df['Snowfall'].apply(lambda x: 1 if x > 2 else 0)
    heavysnowfall = heavysnowfallDf.sum()

    windy8550Df = df.apply(lambda x: 1 if x['W_Spd_8550_AVG']> 40 else 0, axis=1)
    windy8550 = windy8550Df.sum()

    windy10500Df = df.apply(lambda x: 1 if x['W_Spd_10500_AVG']> 30 else 0, axis=1)
    windy10500 = windy10500Df.sum()

    windy11068Df = df.apply(lambda x: 1 if x['W_Spd_11068_AVG']> 40 else 0, axis=1)
    windy11068 = windy11068Df.sum()

    heavysnowDf = df.apply(lambda x: calcSnowDensity(x), axis=1)
    heavysnowDf = heavysnowDf.apply(lambda x: 1 if x > .101 else 0)
    heavySnow = heavysnowDf.sum()

    headers=['DATE','SNOWFALL', 'PERIOD_OF_HEAVY_SNOWFALL','WET_SNOW', 'HEAVY_WIND_8550', 'HEAVY_WIND_10500', 'HEAVY_WIND_11068']
    index = np.array([[df['DATE'].iloc[0], snowfall, heavysnowfall, heavySnow, windy8550, windy8550, windy11068]])
    return pd.DataFrame(data=index,columns=headers)

def doItAll():
    filename = downloadFile()
    print(filename)
    df = preprocessData(filename)
    dailyDf = analyzeData(df)
    updateDB('daily_data', dailyDf)
    df.drop('Snowfall', inplace=True, axis=1)
    updateDB('whole_day_data', df)


if __name__ == "__main__":
    schedule.every().day.at("00:00").do(doItAll)

    while True:
        schedule.run_pending()
        time.sleep(60) # wait one minute