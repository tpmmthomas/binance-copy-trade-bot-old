import time
import pandas as pd
import config.config as cfg
from selenium import webdriver
from bs4 import BeautifulSoup
import threading
from datetime import datetime
import queue

q = queue.Queue(60)
def format_results(x,y):
    words = []
    prev_idx =  0
    for i,ch in enumerate(x):
        result = y.find(x[prev_idx:i])
        if result == -1:
            words.append(x[prev_idx:i-1])
            prev_idx = i-1
    words.append(x[prev_idx:])
    times = words[0]
    words = words[6:]
    symbol = words[::5]
    size = words[1::5]
    entry_price=words[2::5]
    mark_price=words[3::5]
    pnl=words[4::5]
    dictx={"symbol":symbol,"size":size,"Entry Price":entry_price,"Mark Price":mark_price,"PNL (ROE%)":pnl}
    df = pd.DataFrame(dictx)
    return {"time":times,"data":df}

class FetchLatestPosition(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        options = webdriver.ChromeOptions()
        options.binary_location = cfg.chrome_location
        options.add_argument("--headless")
        options.add_argument("--disable-web-security")
        self.driver = webdriver.Chrome(cfg.driver_location,options=options)
        self.prev_df = None
    def run(self):
        while True:
            isChanged = False
            self.driver.get(cfg.position_url)
            time.sleep(1.5)
            soup = BeautifulSoup(self.driver.page_source,features="html.parser")
            x = soup.get_text()
            ### THIS PART IS ACCORDING TO THE CURRENT WEBPAGE DESIGN WHICH MIGHT BE CHANGED
            x = x.split('\n')[4]
            idx = x.find("Position")
            idx2 = x.find("Start")
            x = x[idx:idx2]
            #######################################################################
            try:
                output = format_results(x,self.driver.page_source)
            except:
                continue
            if output["data"].empty:
                continue
            else:
                print(output["data"])
            if self.prev_df is None:
                isChanged = True
            else:
                try:
                    toComp = output["data"][["symbol","size","Entry Price"]]
                except:
                    continue
                if not toComp.equals(self.prev_df):
                    isChanged=True
            if isChanged:
                now = datetime.now()
                q.put(now)
                with open(cfg.save_file,"a",encoding='utf-8') as f:
                    f.write("Current time: "+str(now)+"\n")
                    f.write(output["time"]+"\n")
                    f.write(output["data"].to_string()+"\n")
            self.prev_df = output["data"][["symbol","size","Entry Price"]]
            
            
if __name__ == "__main__":         
    thr = FetchLatestPosition()
    thr.start()
    while True:
        if not q.empty():
            print(q.get())
        else:
            time.sleep(60)
    

