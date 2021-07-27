import constants as cnt
import logging

import telegram
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    ConversationHandler,
    CallbackContext,
)
import time
import pandas as pd
import config.config as cfg
from selenium import webdriver
from bs4 import BeautifulSoup
import threading
from datetime import datetime
import pickle
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException
import math

import urllib3
urllib3.disable_warnings()
# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

logger = logging.getLogger(__name__)

AUTH, COCO,TRADERURL,ALLPROP2,REALSETPROP4,LEVTRADER6,LEVTRADER7,REALSETLEV7,LEVTRADER3,REALSETLEV4,LEVTRADER4,REALSETLEV5,LEVTRADER5,REALSETLEV6, TRADERURL2, LEVTRADER2,REALSETLEV3,TRADERNAME, AUTH2, ANNOUNCE,DISCLAIMER,VIEWTRADER,TP,SL,TOTRADE,TMODE,LMODE,APIKEY,APISECRET,ALLLEV,REALSETLEV,LEVTRADER,LEVSYM,REALSETLEV2,ALLPROP,REALSETPROP,PROPTRADER,PROPSYM,REALSETPROP2,PROPTRADER3,PROPSYM3,REALSETPROP5,PROPTRADER2,PROPSYM2,REALSETPROP3,SAFERATIO= range(46)
CurrentUsers = {}
updater = Updater(cnt.bot_token)
mutex = threading.Lock()
options = webdriver.ChromeOptions()
options.binary_location = cfg.chrome_location
options.add_argument("--headless")
options.add_argument("--disable-web-security")
UserLocks = {}

def format_results(x,y):
    words = []
    prev_idx =  0
    i = 0
    while i<len(x):
        result = y.find(x[prev_idx:i])
        if result == -1:
            while i>=0 and y.find(x[prev_idx:i-1]+"<") == -1:
                i -= 1
            words.append(x[prev_idx:i-1])
            prev_idx = i-1
        i += 1
    words.append(x[prev_idx:])
    times = words[0]
    words = words[6:]
    symbol = words[::5]
    size = words[1::5]
    entry_price=words[2::5]
    mark_price=words[3::5]
    pnl=words[4::5]
    margin = []
    calculatedMargin = []
    for i in range(len(mark_price)):
        idx1 = pnl[i].find("(")
        idx2 = pnl[i].find("%")
        percentage = float(pnl[i][idx1+1:idx2].replace(",",""))/100
        if float(entry_price[i].replace(",","")) == 0:
            margin.append("nan")
            calculatedMargin.append(False)
            continue
        price = (float(mark_price[i].replace(",",""))-float(entry_price[i].replace(",","")))/float(entry_price[i].replace(",",""))
        if percentage == 0 or price == 0:
            margin.append("nan")
            calculatedMargin.append(False)
        else:
            estimated_margin = abs(round(percentage/price))
            calculatedMargin.append(True)
            margin.append(str(estimated_margin)+"x")
        
    dictx={"symbol":symbol,"size":size,"Entry Price":entry_price,"Mark Price":mark_price,"PNL (ROE%)":pnl,"Estimated Margin":margin}
    df = pd.DataFrame(dictx)
    return {"time":times,"data":df},calculatedMargin

def format_username(x,y):
    words = []
    prev_idx =  0
    for i,ch in enumerate(x):
        result = y.find(x[prev_idx:i])
        if result == -1:
            words.append(x[prev_idx:i-1])
            prev_idx = i-1
    words.append(x[prev_idx:])
    return words[-1]

class FetchLatestPosition(threading.Thread):
    def __init__(self,listSymbols,fetch_url,chat_id,name,uname,toTrade,tp=-1,sl=-1,tmode=None,lmode=None,proportion=None,leverage=None,positions=None):
        threading.Thread.__init__(self)
        self.prev_df = None
        self.isStop = threading.Event()
        self.fetch_url = fetch_url
        self.num_no_data = 0
        self.chat_id = chat_id
        self.name = name
        self.uname = uname
        self.runtimes = 0
        self.driver = None
        self.first_run = True
        self.error = 0
        self.toTrade = toTrade
        self.positions= positions
        self.tmodes = tmode
        self.needprop = False
        self.needlev = False
        self.needtmode = False
        if self.positions is None:
            self.positions = {}
        if self.tmodes is None or isinstance(self.tmodes,int):
            self.tmodes = {}
            self.needtmode = True
        if toTrade:
            self.take_profit_percent = {}
            self.stop_loss_percent = {}
            self.proportion = proportion
            self.leverage = leverage
            if self.proportion is None:
                self.proportion = {}
                self.needprop = True
            if self.leverage is None:
                self.leverage = {}
                self.needlev = True
            self.lmode = lmode
            for symbol in listSymbols:
                if self.needprop:
                    self.proportion[symbol] = 0
                if self.needlev:
                    self.leverage[symbol] = 20
                if self.needtmode:
                    self.tmodes[symbol] = tmode
                self.take_profit_percent[symbol] = tp
                self.stop_loss_percent[symbol] = sl
    
    def get_trader_profile(self):
        if self.toTrade:
            return {"url":self.fetch_url,"name":self.name,"uname":self.uname,"trade":self.toTrade,"tmodes":self.tmodes,"tp":self.take_profit_percent,"sl":self.stop_loss_percent,"lmode":self.lmode,"proportion":self.proportion,"leverage":self.leverage,"positions":self.positions}
        return {"url":self.fetch_url,"name":self.name,"uname":self.uname,"trade":self.toTrade}

    def changes(self,df,df2):
        txtype = []
        txsymbol = []
        txsize = []
        executePrice = []
        if isinstance(df,str):
            for index,row in df2.iterrows():
                size = row['size']
                if isinstance(size,str):
                    size = size.replace(",","")
                size = float(size)
                if size >0:
                    txtype.append("OpenLong")
                    txsymbol.append(row['symbol'])
                    txsize.append(size)
                    executePrice.append(row["Entry Price"])
                else:
                    txtype.append("OpenShort")
                    txsymbol.append(row['symbol'])
                    txsize.append(size)
                    executePrice.append(row["Entry Price"])
            txs = pd.DataFrame({"txtype":txtype,"symbol":txsymbol,"size":txsize,"ExecPrice":executePrice})
        elif isinstance(df2,str):
            for index,row in df.iterrows():
                size = row['size']  
                if isinstance(size,str):
                    size = size.replace(",","")
                size = float(size)
                if size > 0:
                    txtype.append("CloseLong")
                    txsymbol.append(row['symbol'])
                    txsize.append(-size)
                    executePrice.append(row["Mark Price"])
                else:
                    txtype.append("CloseShort")
                    txsymbol.append(row['symbol'])
                    txsize.append(-size)
                    executePrice.append(row["Mark Price"])
            txs = pd.DataFrame({"txtype":txtype,"symbol":txsymbol,"size":txsize,"ExecPrice":executePrice})
        else:
            df,df2 = df.copy(),df2.copy()
            for index,row in df.iterrows():
                hasChanged = False
                temp = df2['symbol'] == row['symbol']
                idx = df2.index[temp]
                size = row['size']  
                if isinstance(size,str):
                    size = size.replace(",","")
                size = float(size)
                oldentry = row['Entry Price']  
                if isinstance(oldentry,str):
                    oldentry = oldentry.replace(",","")
                oldentry = float(oldentry)
                oldmark = row['Mark Price']  
                if isinstance(oldmark,str):
                    oldmark = oldmark.replace(",","")
                oldmark = float(oldmark)
                isPositive = size >=0
                for r in idx:
                    df2row = df2.loc[r].values
                    newsize = df2row[1]
                    if isinstance(newsize,str):
                        newsize = newsize.replace(",","")
                    newsize = float(newsize)
                    newentry = df2row[2]
                    if isinstance(newentry,str):
                        newentry = newentry.replace(",","")
                    newentry = float(newentry)
                    newmark = df2row[3]
                    if isinstance(newmark,str):
                        newmark = newmark.replace(",","")
                    newmark = float(newmark)
                    if newsize == size:
                        df2 = df2.drop(r)
                        hasChanged = True
                        break
                    if isPositive and newsize > 0:
                        changesize = newsize-size
                        if changesize > 0:
                            txtype.append("OpenLong")
                            txsymbol.append(df2row[0])
                            txsize.append(changesize)
                            try:
                                exp = (newentry*newsize-oldentry*size)/changesize
                            except:
                                exp = 0
                            executePrice.append(exp)
                        else:
                            txtype.append("CloseLong")
                            txsymbol.append(df2row[0])
                            txsize.append(changesize)
                            executePrice.append(newmark)
                        df2 = df2.drop(idx)
                        hasChanged = True
                        break
                    if not isPositive and newsize < 0:
                        changesize = newsize - size
                        if changesize > 0:
                            txtype.append("CloseShort")
                            txsymbol.append(df2row[0])
                            txsize.append(changesize)
                            executePrice.append(newmark)
                        else:
                            txtype.append("OpenShort")
                            txsymbol.append(df2row[0])
                            txsize.append(changesize)
                            try:
                                exp = (newentry*newsize-oldentry*size)/changesize
                            except:
                                exp = 0
                            executePrice.append(exp)
                        df2 = df2.drop(r)
                        hasChanged = True
                        break
                if not hasChanged:
                    if size > 0:
                        txtype.append("CloseLong")
                        txsymbol.append(row['symbol'])
                        txsize.append(-size)
                        executePrice.append(oldmark)
                    else:
                        txtype.append("CloseShort")
                        txsymbol.append(row['symbol'])
                        txsize.append(-size)
                        executePrice.append(oldmark)
            for index,row in df2.iterrows():
                size = row['size']  
                if isinstance(size,str):
                    size = size.replace(",","")
                size = float(size)
                if size >0:
                    txtype.append("OpenLong")
                    txsymbol.append(row['symbol'])
                    txsize.append(size)
                    executePrice.append(row['Entry Price'])
                else:
                    txtype.append("OpenShort")
                    txsymbol.append(row['symbol'])
                    txsize.append(size)
                    executePrice.append(row['Entry Price'])
            txs = pd.DataFrame({"txType":txtype,"symbol":txsymbol,"size":txsize,"ExecPrice":executePrice})
        tosend = f"*The positions changed by the trader {self.name}:*\n"+txs.to_string()+"\n"
        updater.bot.sendMessage(chat_id=self.chat_id,text=tosend,parse_mode=telegram.ParseMode.MARKDOWN)
        return txs

    def run(self):
        logger.info("%s starting %s",self.uname,self.name)
        while not self.isStop.is_set():
            isChanged = False
            time.sleep(self.error*2)
            if self.error >=30:
                tosend = f"Hi, it seems that our bot is not able to check {self.name}'s position. This might be due to the trader decided to stop sharing or a bug in our bot. Please /delete this trader and report to us if you think it's a bug.\nIt is possible that you keep following this trader in case their positions open again, but you will keep receiving error messages until then."
                logger.info(f"{self.uname}: Error found in trader {self.name}.")
                updater.bot.sendMessage(chat_id=self.chat_id,text=tosend)
                self.error = 0
            if self.driver is None:
                while True:
                    try:
                        self.driver = webdriver.Chrome(cfg.driver_location,options=options)
                        self.driver.get(self.fetch_url)
                        break
                    except: 
                        time.sleep(0.1)
                        continue
            else:
                try:
                    self.driver.refresh()
                except:
                    self.error += 1
                    time.sleep(60)
                    continue
            time.sleep(5)
            soup = BeautifulSoup(self.driver.page_source,features="html.parser")
            x = soup.get_text()
            ### THIS PART IS ACCORDING TO THE CURRENT WEBPAGE DESIGN WHICH MIGHT BE CHANGED
            x = x.split('\n')[4]
            idx = x.find("Position")
            idx2 = x.find("Start")
            idx3 = x.find("No data")
            x = x[idx:idx2]
            if idx3 != -1:
                self.num_no_data += 1
                if self.num_no_data >=2 and not isinstance(self.prev_df,str):
                    now = datetime.now()
                    tosend = f"Trader {self.name}, Current time: "+str(now)+"\nNo positions.\n"
                    updater.bot.sendMessage(chat_id=self.chat_id,text=tosend)
                    if not self.first_run:
                        txlist = self.changes(self.prev_df,"x")
                        if self.toTrade:
                            UserLocks[self.chat_id].acquire()
                            CurrentUsers[self.chat_id].bclient.open_trade(txlist,self.name,self.proportion,self.leverage,self.lmode,self.tmodes,self.positions,self.take_profit_percent,self.stop_loss_percent)
                            UserLocks[self.chat_id].release()
                if self.num_no_data != 1:
                    self.prev_df = "x"
                    self.first_run = False
                    time.sleep(60)
                time.sleep(5)
                self.runtimes += 1
                if self.runtimes >=15:
                    self.runtimes = 0
                    self.driver.quit()
                    self.driver = None
                continue
            else:
                self.num_no_data = 0
            #######################################################################
            try:
                output,calmargin = format_results(x,self.driver.page_source)
            except:
                self.error += 1
                continue
            if output["data"].empty:
                self.error += 1
                continue
            if self.toTrade and self.lmode == 0:
                symbols = output["data"]["symbol"].values
                margins = output["data"]["Estimated Margin"].values
                for i,mask in enumerate(calmargin):
                    if mask:
                        self.leverage[symbols[i]] = int(margins[i][:-1])
            if self.prev_df is None or isinstance(self.prev_df,str):
                isChanged = True
            else:
                try:
                    toComp = output["data"][["symbol","size","Entry Price"]]
                    prevdf = self.prev_df[["symbol","size","Entry Price"]]
                except:
                    self.error += 1
                    continue
                if not toComp.equals(prevdf):
                    isChanged=True
            if isChanged:
                now = datetime.now()
                tosend = f"Trader {self.name}, Current time: "+str(now)+"\n"+output["time"]+"\n"+output["data"].to_string()+"\n"
                updater.bot.sendMessage(chat_id=self.chat_id,text=tosend)
                if not self.first_run:
                    txlist = self.changes(self.prev_df,output["data"])
                    if self.toTrade:
                        UserLocks[self.chat_id].acquire()
                        CurrentUsers[self.chat_id].bclient.open_trade(txlist,self.name,self.proportion,self.leverage,self.lmode,self.tmodes,self.positions,self.take_profit_percent,self.stop_loss_percent)
                        UserLocks[self.chat_id].release()
            self.prev_df = output["data"]
            self.first_run = False
            self.runtimes += 1
            if self.runtimes >=15:
                self.runtimes = 0
                self.driver.quit()
                self.driver = None
            time.sleep(60)
        if self.driver is not None:
            self.driver.quit()
        updater.bot.sendMessage(chat_id=self.chat_id,text=f"Successfully quit following trader {self.name}.")

    def stop(self):
        self.isStop.set()

    def get_info(self):
        if self.prev_df is not None:
            if isinstance(self.prev_df,str):
                return "No positions."
            return self.prev_df.to_string()
        else:
            return "Error."

    def reload(self):
        if not self.toTrade:
            return
        allsymbols = CurrentUsers[self.chat_id].bclient.get_symbols()
        secondProportion = {}
        secondLeverage = {}
        secondtmodes = {}
        for symbol in allsymbols:
            if symbol in self.proportion:
                secondProportion[symbol] = self.proportion[symbol]
                secondLeverage[symbol] = self.leverage[symbol]
                secondtmodes[symbol] = self.tmodes[symbol]
            else:
                secondProportion[symbol] = 0
                secondLeverage[symbol] = 20
                secondtmodes[symbol] = 0
                updater.bot.sendMessage(chat_id=self.chat_id,text=f"Please note that there is a new symbol {symbol} available. You may want to adjust your settings for it.")
        self.proportion = secondProportion
        self.leverage = secondLeverage
        self.tmodes = secondtmodes

    def change_proportion(self,symbol,prop):
        if symbol not in self.proportion:
            updater.bot.sendMessage(chat_id=self.chat_id,text="Sorry,but this symbol is not available right now.")
        self.proportion[symbol] = prop
        logger.info(f"{self.uname} Successfully changed proportion.")
        updater.bot.sendMessage(chat_id=self.chat_id,text=f"Successfully changed proportion!")
        return

    def get_proportion(self,symbol):
        if symbol not in self.proportion:
            updater.bot.sendMessage(chat_id=self.chat_id,text="Sorry,but this symbol is not available right now.")
            return
        #updater.bot.sendMessage(chat_id=self.chat_id,text=f"The proportion for {symbol} is {self.proportion[symbol]}x.")
        logger.info(f"{self.uname} Successfully queried proportion.")
        return self.proportion[symbol]
    
    def change_all_proportion(self,prop):
        for symbol in self.proportion:
            self.proportion[symbol] = prop
        logger.info(f"{self.uname} Successfully changed all proportion.")
        updater.bot.sendMessage(chat_id=self.chat_id,text=f"Successfully changed proportion!")
        return
    
    def change_leverage(self,symbol,lev):
        if symbol not in self.leverage:
            updater.bot.sendMessage(chat_id=self.chat_id,text="Sorry,but this symbol is not available right now.")
        try:
            lev = int(lev)
            assert lev>=1 and lev<=125
        except:
            updater.bot.sendMessage(chat_id=self.chat_id,text="Sorry,but the leverage must be an integer between 1 and 125.")
            return
        self.leverage[symbol] = lev
        logger.info(f"{self.uname} Successfully changed leverage.")
        updater.bot.sendMessage(chat_id=self.chat_id,text="Successfully changed leverage!")
        return

    def get_leverage(self,symbol):
        if symbol not in self.leverage:
            updater.bot.sendMessage(chat_id=self.chat_id,text="Sorry,but this symbol is not available right now.")
            return
        #updater.bot.sendMessage(chat_id=self.chat_id,text=f"The leverage for {symbol} is {self.leverage[symbol]}x.")
        logger.info(f"{self.uname} Successfully queried leverage.")
        return self.leverage[symbol]
    
    def change_all_leverage(self,lev):
        try:
            lev = int(lev)
            assert lev>=1 and lev<=125
        except:
            updater.bot.sendMessage(chat_id=self.chat_id,text="Sorry,but the leverage must be an integer between 1 and 125.")
            return
        for symbol in self.leverage:
            self.leverage[symbol] = lev
        logger.info(f"{self.uname} Successfully changed all leverage.")
        updater.bot.sendMessage(chat_id=self.chat_id,text="Successfully changed leverage!")
        return

    def change_tmode(self,symbol,tmode):
        if symbol not in self.tmodes:
            updater.bot.sendMessage(chat_id=self.chat_id,text="Sorry,but this symbol is not available right now.")
        try:
            tmode = int(tmode)
            assert tmode>=0 and tmode<=2
        except:
            updater.bot.sendMessage(chat_id=self.chat_id,text="Sorry,but the order mode must be an integer between 0 and 2.")
            return
        self.tmodes[symbol] = tmode
        logger.info(f"{self.uname} Successfully changed tmode.")
        updater.bot.sendMessage(chat_id=self.chat_id,text="Successfully changed order mode!")
        return

    def get_tmode(self,symbol):
        if symbol not in self.tmodes:
            updater.bot.sendMessage(chat_id=self.chat_id,text="Sorry,but this symbol is not available right now.")
            return
        #updater.bot.sendMessage(chat_id=self.chat_id,text=f"The leverage for {symbol} is {self.leverage[symbol]}x.")
        logger.info(f"{self.uname} Successfully queried tmode.")
        return self.tmodes[symbol]
    
    def change_all_tmode(self,tmode):
        try:
            tmode = int(tmode)
            assert tmode>=0 and tmode<=2
        except:
            updater.bot.sendMessage(chat_id=self.chat_id,text="Sorry,but the order mode must be an integer between 0 and 2.")
            return
        for symbol in self.tmodes:
            self.tmodes[symbol] = tmode
        logger.info(f"{self.uname} Successfully changed all tmode.")
        return

    def change_lmode(self,lmode):
        try:
            lmode = int(lmode)
            assert lmode >=0 and lmode <=2
        except:
            updater.bot.sendMessage(chat_id=self.chat_id,text="Sorry,but the leverage mode must be an integer between 0 and 2.")
            return
        self.lmode = lmode
        logger.info(f"{self.uname} Successfully changed lmode.")
        #updater.bot.sendMessage(chat_id=self.chat_id,text="Successfully changed leverage mode!")
        return

    def get_tpsl(self,symbol):
        if symbol not in self.take_profit_percent:
            updater.bot.sendMessage(chat_id=self.chat_id,text="Sorry,but this symbol is not available right now.")
            return
        #updater.bot.sendMessage(chat_id=self.chat_id,text=f"The leverage for {symbol} is {self.leverage[symbol]}x.")
        logger.info(f"{self.uname} Successfully queried profit/loss percentages.")
        return self.take_profit_percent[symbol],self.stop_loss_percent[symbol]
    
    def change_all_tpsl(self,tp,sl):
        try:
            tp = int(tp)
            sl = int(sl)
            assert tp>=-1 and tp<=400 and sl>=-1 and sl<=400
        except:
            updater.bot.sendMessage(chat_id=self.chat_id,text="Sorry,but the profit and loss percentage must be an integer between 0 and 400, or -1 if you don't want to set.")
            return
        for symbol in self.take_profit_percent:
            self.take_profit_percent[symbol] = tp
            self.stop_loss_percent[symbol] = sl
        logger.info(f"{self.uname} Successfully changed all take profit/stop loss percentages.")
        return

    def change_tpsl(self,symbol,tp,sl):
        if symbol not in self.take_profit_percent:
            updater.bot.sendMessage(chat_id=self.chat_id,text="Sorry,but this symbol is not available right now.")
            return
        try:
            tp = int(tp)
            sl = int(sl)
            assert tp>=-1 and tp<=400 and sl>=-1 and sl<=400
        except:
            updater.bot.sendMessage(chat_id=self.chat_id,text="Sorry,but the profit and loss percentage must be an integer between 0 and 400, or -1 if you don't want to set.")
            return
        self.take_profit_percent[symbol] = tp
        self.stop_loss_percent[symbol] = sl
        logger.info(f"{self.uname} Successfully changed profit/loss percentage.")
        #updater.bot.sendMessage(chat_id=self.chat_id,text="Successfully changed leverage mode!")
        return

def retrieveUserName(url):
    success = False
    name = ""
    while True:
        try:
            myDriver = webdriver.Chrome(cfg.driver_location,options=options)
            break
        except: 
            time.sleep(0.1)
            continue
    while not success or name == "No Battle Record Found":
        try:
            myDriver.get(url)
        except:
            return None
        time.sleep(2)
        soup = BeautifulSoup(myDriver.page_source,features="html.parser")
        x = soup.get_text()
        x = x.split('\n')[4]
        idx = x.find("'s")
        x = x[idx-30:idx]
        try:
            name = format_username(x,myDriver.page_source)
            success = True
        except:
            continue
    myDriver.quit()
    return name

def start(update: Update, context: CallbackContext) -> int:
    if update.message.chat_id in CurrentUsers:
        update.message.reply_text("You have already initalized! Please use other commands, or use /end to end current session before initializing another.")
        return ConversationHandler.END
    update.message.reply_text(
        f'*Welcome {update.message.from_user.first_name}!* Before you start, please type in the access code (6 digits).',
        parse_mode=telegram.ParseMode.MARKDOWN
    )
    context.user_data['uname'] = update.message.from_user.first_name
    return AUTH

def auth_check(update: Update, context: CallbackContext) -> int:
    user = update.message.from_user
    logger.info("%s is doing authentication check.", update.message.from_user.first_name)
    if update.message.text == cnt.auth_code:
        update.message.reply_text(
            'Great! Please read the following disclaimer:\nThis software is for non-commercial purposes only.\n\
Do not risk money which you are afraid to lose.\nUSE THIS SOFTWARE AT YOUR OWN RISK.\n*THE DEVELOPERS ASSUME NO RESPONSIBILITY FOR YOUR TRADING RESULTS.*\n\
Do not engage money before you understand how it works and what profit/loss you should expect. \n\
Type "yes" (lowercase) if you agree. Otherwise type /cancel and exit.',
            parse_mode=telegram.ParseMode.MARKDOWN
        )
        return DISCLAIMER
    else:
        update.message.reply_text("Sorry! The access code is wrong. Type /start again if you need to retry.")
        return ConversationHandler.END

def disclaimer_check(update: Update, context: CallbackContext):
    logger.info("%s has agreed to the disclaimer.", update.message.from_user.first_name)
    update.message.reply_text("Please provide your API Key from Binance.")
    update.message.reply_text("*SECURITY WARNING*\nTo ensure safety of funds, please note the following before providing your API key:\n1. Set up a new key for this program, don't reuse your other API keys.\n2. Restrict access to this IP: *35.229.163.161*\n3. Only allow these API Restrictions: 'Enable Reading' and 'Enable Futures'.",parse_mode=telegram.ParseMode.MARKDOWN)
    return APIKEY

def check_api(update: Update, context: CallbackContext):
    context.user_data['api_key'] = update.message.text
    update.message.reply_text("Please provide your Secret Key.\n*DELETE YOUR MESSAGE IMMEDIATELY AFTERWARDS.*",parse_mode=telegram.ParseMode.MARKDOWN) 
    return APISECRET

def check_secret(update: Update, context: CallbackContext):
    context.user_data['api_secret'] = update.message.text
    update.message.reply_text("To protect your funds, you are required to enter a safe ratio as a threshold in which trades will be opened.\nIf your account's available balance * safe ratio <= the margin required, the trade will not be set up.\n(Enter a number between 0 and 1.)")
    return SAFERATIO

def check_ratio(update: Update, context: CallbackContext):
    try:
        ratio = float(update.message.text)
        assert ratio>=0 and ratio<=1
    except:
        update.message.reply_text("Sorry, the ratio is invalid. Please enter again.")
        return SAFERATIO
    context.user_data['safe_ratio'] = ratio
    update.message.reply_text("Now, please provide the UID of the trader you want to follow. (can be found in the trader's URL)")
    return TRADERURL 

def initTraderThread(chat_id,uname,safe_ratio,init_trader,trader_name,api_key,api_secret,toTrade,tmode,lmode,tp,sl):
    UserLocks[chat_id] = threading.Lock() #when calling binance client, have to use the lock.
    if toTrade:
        CurrentUsers[chat_id] = users(chat_id,uname,safe_ratio,init_trader,trader_name,api_key,api_secret,toTrade,tp,sl,tmode,lmode)
    else:
        CurrentUsers[chat_id] = users(chat_id,uname,safe_ratio,init_trader,trader_name,api_key,api_secret,toTrade)
    
    updater.bot.sendMessage(
        chat_id = chat_id,
        text=f'Thanks! You will start receiving alerts when {trader_name} changes positions.\nHere is a list of available commands:'
    )
    updater.bot.sendMessage(chat_id=chat_id,text='***GENERAL***\n/start: Initalize and begin following traders\n/add: add a trader\n/delete: remove a trader\n/admin: Announce message to all users (need authorization code)\n/help: view list of commands\n/view : view a trader current position.\n/end: End the service.\n***TRADE COPY CONFIG***\n/setproportion: Set the trade copy proportion for a (trader,symbol) pair.\n/setallproportion: Set the trade copy proportion for a trader, all symbols.\n/getproportion: Get the current proportion for a (trader,symbol) pair\n/setleverage: set leverage for a (trader,symbol) pair.\n/setallleverage: set leverage for a trader, all symbols.\n/getleverage: Get the current leverage for the (trader,symbol) pair.\n/setlmode: Change the leverage mode of a trader.\n/settmode: Change the trading mode for a (trader,symbol) pair.\n/setalltmode: Change trading mode for a trader, all symbols.\n/changesr: Change safety ratio\n/gettpsl: Get the take profit/stop loss ratio of a (trader,symbol) pair.\n/settpsl: Set the take profit/stop loss ratio of a (trader,symbol) pair.\n/setalltpsl: Set the take profit/stop loss ratio of a trader, all symbols.')
    if toTrade:
        updater.bot.sendMessage(chat_id= chat_id, text="*All your proportions have been set to 0x and all leverage has ben set to 20x (if applicable). Change these settings with extreme caution.*",parse_mode=telegram.ParseMode.MARKDOWN)

def url_check(update: Update, context: CallbackContext) -> int:
    url = update.message.text
    user = update.message.from_user
    update.message.reply_text("Please wait...")
    logger.info("%s has entered the first url.", update.message.from_user.first_name)
    try:
        url =  "https://www.binance.com/en/futures-activity/leaderboard/user?uid="+url+"&tradeType=PERPETUAL"
        myDriver = webdriver.Chrome(cfg.driver_location,options=options)
        myDriver.get(url)
    except:
        update.message.reply_text("Sorry! Your UID is invalid. Please try entering again.")
        return TRADERURL
    myDriver.quit()
    traderName = retrieveUserName(url)
    if traderName is None:
        update.message.reply_text("Sorry! Your UID is invalid. Please try entering again.")
        return TRADERURL
    context.user_data['url'] = url
    context.user_data['name'] = traderName
    context.user_data["First"] = True
    update.message.reply_text(f"Do you want us to copy the positions of {traderName} automatically, or do you only want to follow and get alerts?") 
    update.message.reply_text("Pick 'yes' to set up copy trade, 'no' to just follow.",
        reply_markup=ReplyKeyboardMarkup([['yes','no']],one_time_keyboard=True)
    )
    return TOTRADE

def trade_confirm(update: Update, context: CallbackContext):
    response = update.message.text
    if response == "yes":
        context.user_data['toTrade'] = True
    else:
        context.user_data['toTrade'] = False
        if context.user_data['First']:
            t1 = threading.Thread(target=initTraderThread,args=(update.message.chat_id,context.user_data['uname'],context.user_data['safe_ratio'],context.user_data['url'],context.user_data['name'],context.user_data['api_key'],context.user_data['api_secret'],context.user_data['toTrade'],-1,-1))
            t1.start()
        else:
            t1 = threading.Thread(target=addTraderThread,args=(update.message.chat_id,context.user_data['uname'],context.user_data['url'],context.user_data['name'],context.user_data['toTrade'],-1,-1,-1,-1))
            t1.start()
        return ConversationHandler.END
    update.message.reply_text("Please select the default trading mode:")
    update.message.reply_text("0. MARKET: Once we detected a change in position, you will make an order immediately at the market price. As a result, your entry price might deviate from the trader's entry price (especially when there are significant market movements).") 
    update.message.reply_text("1. LIMIT: You will make an limit order at the same price as the trader's estimated entry price. However, due to fluctuating market movements, your order might not be fulfilled.")
    update.message.reply_text("2. LIMIT, THEN MARKET: When opening positions, you will make an limit order at the same price as the trader's estimated entry price. When closing positions, you will follow market.")
    update.message.reply_text("Please type 0,1 or 2 to indicate your choice. Note that you can change it later for every (trader,symbol) pair.")
    return TMODE

def tmode_confirm(update: Update, context: CallbackContext):
    context.user_data['tmode'] = int(update.message.text)
    update.message.reply_text("Please select the leverage mode:")
    update.message.reply_text("0. FOLLOW: You will follow the same leverage as the trader. However, note that the leverage is only an estimate. In case the leverage information cannot be obtained, we would look at the trader's history leverage on the given symbol to determine the leverage. If that was not available as well, a default of 20x leverage would be used.") 
    update.message.reply_text("1. FIXED: You can fix your own leverage settings within this bot for every (trader,symbol) combination. Once we place an order, the leverage set by you will be used regardless of the trader's leverage. Default is 20x and can be changed later.")
    update.message.reply_text("2: IGNORE: You will follow the leverage settings on the binance site, we will not attempt to change any leverage settings for you.")
    update.message.reply_text("Please type 0,1 or 2 to indicate your choice.")
    return LMODE

def lmode_confirm(update: Update, context: CallbackContext):
    context.user_data['lmode'] = int(update.message.text)
    update.message.reply_text("Please enter your *take profit* percentage. With every order you successfully created, we will place a take profit order if the ROE exceeds a certain pecentage.", parse_mode=telegram.ParseMode.MARKDOWN)
    update.message.reply_text("Please enter an integer from 0 to 400, and -1 if you do not want to have a take profit order.")
    return TP

def tp_confirm(update: Update, context: CallbackContext):
    tp = update.message.text
    try:
        tp = int(tp)
        assert tp>=-1 and tp<=400
    except:
        update.message.reply_text("Sorry but the percentage is not valid. Please enter again (integer between 0 and 400, or -1 if do not want to set)")
        return TP
    context.user_data['tp'] = tp
    update.message.reply_text("Please enter the *stop loss* percentage now. (integer between 0 and 400, or -1 if you do not want to set)" ,parse_mode=telegram.ParseMode.MARKDOWN)
    return SL
    
def sl_confirm(update: Update, context: CallbackContext):
    sl = update.message.text
    try:
        sl = int(sl)
        assert sl>=-1 and sl<=400
    except:
        update.message.reply_text("Sorry but the percentage is not valid. Please enter again (integer between 0 and 400, or -1 if do not want to set)")
        return SL
    update.message.reply_text("Please wait...")
    if context.user_data['First']:
        t1 = threading.Thread(target=initTraderThread,args=(update.message.chat_id,context.user_data['uname'],context.user_data['safe_ratio'],context.user_data['url'],context.user_data['name'],context.user_data['api_key'],context.user_data['api_secret'],context.user_data['toTrade'],context.user_data['tmode'],context.user_data['lmode'],context.user_data["tp"],sl))
        t1.start()
    else:
        t1 = threading.Thread(target=addTraderThread,args=(update.message.chat_id,context.user_data['uname'],context.user_data['url'],context.user_data['name'],context.user_data['toTrade'],context.user_data['tmode'],context.user_data['lmode'],context.user_data["tp"],sl))
        t1.start()
    return ConversationHandler.END    
    
def cancel(update: Update, context: CallbackContext) -> int:
    """Cancels and ends the conversation."""
    user = update.message.from_user
    logger.info("User %s canceled the conversation.", update.message.from_user.first_name)
    update.message.reply_text(
        'Operation canceled.', reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

def add_trader(update: Update, context: CallbackContext) -> int:
    if not update.message.chat_id in CurrentUsers:
        update.message.reply_text("Please initalize with /start first.")
        return ConversationHandler.END
    if CurrentUsers[update.message.chat_id].is_handling:
        update.message.reply_text("You are adding another trader, wait for it to complete first!")
        return ConversationHandler.END
    context.user_data['uname'] = update.message.from_user.first_name
    update.message.reply_text(
        "Please enter UID of the trader you want to add. (can be found in the trader's URL)"
    )
    return TRADERURL2

def addTraderThread(chat_id,uname,url,trader_name,toTrade,tmode,lmode,tp,sl):
    if trader_name in CurrentUsers[chat_id].trader_names:
        updater.bot.sendMessage(chat_id=chat_id,text="You already followed this trader.")
        mutex.acquire()
        CurrentUsers[chat_id].is_handling = False
        mutex.release()
        return
    logger.info("%s has added trader %s.", uname,trader_name)
    updater.bot.sendMessage(
        chat_id = chat_id,
        text=f'Thanks! You will start receiving alerts when {trader_name} changes positions.'
    )
    CurrentUsers[chat_id].add_trader(url,trader_name,toTrade,tp,sl,tmode,lmode)
    mutex.acquire()
    CurrentUsers[chat_id].is_handling = False
    mutex.release()

def url_add(update: Update, context: CallbackContext) -> int:
    url = update.message.text
    update.message.reply_text("Please wait...", reply_markup=ReplyKeyboardRemove())
    try:
        url =  "https://www.binance.com/en/futures-activity/leaderboard/user?uid="+url+"&tradeType=PERPETUAL"
        myDriver = webdriver.Chrome(cfg.driver_location,options=options) 
        myDriver.get(url)
    except:
        update.message.reply_text("Sorry! Your URL is invalid. Please try entering again.")
        return TRADERURL2
    myDriver.quit()
    traderName = retrieveUserName(url)
    if traderName is None:
        update.message.reply_text("Sorry! Your URL is invalid. Please try entering again.")
        return TRADERURL2
    context.user_data['url'] = url
    context.user_data['name'] = traderName
    context.user_data['First'] = False
    mutex.acquire()
    CurrentUsers[update.message.chat_id].is_handling = True
    mutex.release()
    update.message.reply_text(f"Do you want us to copy the positions of {traderName} automatically, or do you only want to follow and get alerts?") 
    update.message.reply_text("Pick 'yes' to set up copy trade, 'no' to just follow.",
        reply_markup=ReplyKeyboardMarkup([['yes','no']],one_time_keyboard=True)
    )
    return TOTRADE
    # 
    
    # t1 = threading.Thread(target=addTraderThread,args=(url,update.message.chat_id,update.message.from_user.first_name))
    # t1.start()
    # return ConversationHandler.END

def help_command(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /help is issued."""
    update.message.reply_text('***GENERAL***\n/start: Initalize and begin following traders\n/add: add a trader\n/delete: remove a trader\n/admin: Announce message to all users (need authorization code)\n/help: view list of commands\n/view : view a trader current position.\n/end: End the service.\n***TRADE COPY CONFIG***\n/setproportion: Set the trade copy proportion for a (trader,symbol) pair.\n/setallproportion: Set the trade copy proportion for a trader, all symbols.\n/getproportion: Get the current proportion for a (trader,symbol) pair\n/setleverage: set leverage for a (trader,symbol) pair.\n/setallleverage: set leverage for a trader, all symbols.\n/getleverage: Get the current leverage for the (trader,symbol) pair.\n/setlmode: Change the leverage mode of a trader.\n/settmode: Change the trading mode for a (trader,symbol) pair.\n/setalltmode: Change trading mode for a trader, all symbols.\n/changesr: Change safety ratio\n/gettpsl: Get the take profit/stop loss ratio of a (trader,symbol) pair.\n/settpsl: Set the take profit/stop loss ratio of a (trader,symbol) pair.\n/setalltpsl: Set the take profit/stop loss ratio of a trader, all symbols.')

def split(a, n):
    if n==0:
        return [a]
    k, m = divmod(len(a), n)
    return [a[i * k + min(i, m):(i + 1) * k + min(i + 1, m)] for i in range(n)]

def delete_trader(update: Update, context: CallbackContext):
    if not update.message.chat_id in CurrentUsers:
        update.message.reply_text("Please initalize with /start first.")
        return ConversationHandler.END
    if CurrentUsers[update.message.chat_id].is_handling:
        update.message.reply_text("You are adding another trader, wait for it to complete first!")
        return ConversationHandler.END
    listtraders = CurrentUsers[update.message.chat_id].trader_names
    if len(listtraders) == 0:
        update.message.reply_text("You are not following any traders.")
        return ConversationHandler.END
    listtraders = split(listtraders,len(listtraders)//2)
    update.message.reply_text("Please choose the trader to remove.\n(/cancel to cancel)",
        reply_markup=ReplyKeyboardMarkup(listtraders,one_time_keyboard=True,input_field_placeholder="Which Trader?")
        )
    return TRADERNAME

def view_trader(update: Update, context: CallbackContext):
    if not update.message.chat_id in CurrentUsers:
        update.message.reply_text("Please initalize with /start first.")
        return ConversationHandler.END
    if CurrentUsers[update.message.chat_id].is_handling:
        update.message.reply_text("You are adding another trader, wait for it to complete first!")
        return ConversationHandler.END
    listtraders = CurrentUsers[update.message.chat_id].trader_names
    if len(listtraders) == 0:
        update.message.reply_text("You are not following any traders.")
        return ConversationHandler.END
    listtraders = split(listtraders,len(listtraders)//2)
    update.message.reply_text("Please choose the trader to view.\n(/cancel to cancel)",
        reply_markup=ReplyKeyboardMarkup(listtraders,one_time_keyboard=True,input_field_placeholder="Which Trader?")
        )
    return VIEWTRADER

def view_traderInfo(update: Update, context: CallbackContext):
    user = CurrentUsers[update.message.chat_id]
    try:
        idx = user.trader_names.index(update.message.text)
    except:
        update.message.reply_text("This is not a valid trader.")
        return ConversationHandler.END
    update.message.reply_text(f"{update.message.text}'s current position:")
    update.message.reply_text(f"{user.threads[idx].get_info()}")
    #update.message.reply_text(f"Successfully removed {update.message.text}.")
    return ConversationHandler.END

def delTrader(update: Update, context: CallbackContext):
    user = CurrentUsers[update.message.chat_id]
    logger.info("deleting trader %s.",update.message.text)
    try:
        idx = user.trader_names.index(update.message.text)
    except:
        update.message.reply_text("This is not a valid trader.")
        return ConversationHandler.END
    update.message.reply_text("Please wait. It takes around 1 min...")
    user.delete_trader(idx)
    #update.message.reply_text(f"Successfully removed {update.message.text}.")
    return ConversationHandler.END

def end_all(update:Update, context: CallbackContext):
    if not update.message.chat_id in CurrentUsers:
        update.message.reply_text("Please initalize with /start first.")
        return
    if CurrentUsers[update.message.chat_id].is_handling:
        update.message.reply_text("You are adding another trader, wait for it to complete first!")
        return
    logger.info("%s ended the service.",update.message.from_user.first_name)
    update.message.reply_text("Confirm ending the service? This means that we will not make trades for you anymore and you have to take care of the positions previously opened by yourself. Type 'yes' to confirm, /cancel to cancel.")
    return COCO

def realEndAll(update:Update, context: CallbackContext):
    user = CurrentUsers[update.message.chat_id]
    for thread in user.threads:
        thread.stop()
    del CurrentUsers[update.message.chat_id]
    update.message.reply_text("Sorry to see you go. You can press /start to restart the service.")
    return ConversationHandler.END

def end_everyone(update:Update, context: CallbackContext):
    for user in CurrentUsers:
        user = CurrentUsers[user]
        for thread in user.threads:
            thread.stop()
        updater.bot.sendMessage(chat_id=user.chat_id,text="Your service has been force ended by admin.")
    logger.info("Everyone's service has ended.")
    return ConversationHandler.END
    
def admin(update:Update, context: CallbackContext):
    update.message.reply_text("Please enter admin authorization code to continue.")
    return AUTH2

def auth_check2(update: Update, context: CallbackContext) -> int:
    user = update.message.from_user
    logger.info("%s is doing authentication check for admin.", update.message.from_user.first_name)
    if update.message.text == cnt.admin_code:
        update.message.reply_text(
            'Great! Please enter the message that you want to announce to all users. /cancel to cancel, /save to save users data, /endall to end all users.'
        )
        return ANNOUNCE
    else:
        update.message.reply_text("Sorry! The access code is wrong. Type /admin again if you need to retry.")
        return ConversationHandler.END

def announce(update: Update, context: CallbackContext):
    for user in CurrentUsers:
        updater.bot.sendMessage(chat_id=user,text=update.message.text)
    logger.info("Message announced for all users.")
    return ConversationHandler.END

def save_to_file(update: Update, context: CallbackContext):
    save_items = []
    for user in CurrentUsers:
        user = CurrentUsers[user]
        traderProfiles = []
        for trader in user.threads:
            traderProfiles.append(trader.get_trader_profile())
        save_items.append({"chat_id":user.chat_id,"profiles":traderProfiles,"safety_ratrio":user.bclient.safety_ratio,"api_key":user.api_key,"api_secret":user.api_secret})
    with open("userdata.pickle",'wb') as f:
        pickle.dump(save_items,f)
    logger.info("Saved user current state.")
    return ConversationHandler.END

def automatic_reload():
    while True:
        time.sleep(60*60*24)
        for users in CurrentUsers:
            UserLocks[users].acquire()
            CurrentUsers[users].bclient.reload()
            UserLocks[users].release()
            for traders in users.threads:
                traders.reload()
            time.sleep(60)
        save_to_file(None,None)
    
def set_all_leverage(update: Update, context: CallbackContext):
    if not update.message.chat_id in CurrentUsers:
        update.message.reply_text("Please initalize with /start first.")
        return ConversationHandler.END
    if CurrentUsers[update.message.chat_id].is_handling:
        update.message.reply_text("You are adding another trader, wait for it to complete first!")
        return ConversationHandler.END
    listtraders = CurrentUsers[update.message.chat_id].trader_names
    if len(listtraders) == 0:
        update.message.reply_text("You are not following any traders.")
        return ConversationHandler.END
    listtraders = split(listtraders,len(listtraders)//2)
    update.message.reply_text("Please choose the trader to set leverage for all symbols.\n(/cancel to cancel)",
        reply_markup=ReplyKeyboardMarkup(listtraders,one_time_keyboard=True,input_field_placeholder="Which Trader?")
        )
    return ALLLEV

def setAllLeverage(update: Update, context: CallbackContext):
    user = CurrentUsers[update.message.chat_id]
    logger.info(f"User {user.uname} adjusting leverage.")
    try:
        idx = user.trader_names.index(update.message.text)
    except:
        update.message.reply_text("This is not a valid trader.")
        return ConversationHandler.END
    if not user.threads[idx].toTrade:
        update.message.reply_text("You did not set copy trade option for this trader. If needed, /delete this trader and /add again.")
        return ConversationHandler.END
    context.user_data['idx'] = idx
    update.message.reply_text("Please enter the target leverage (Integer between 1 and 125)")
    return REALSETLEV

def setAllLeverageReal(update: Update, context: CallbackContext):
    user = CurrentUsers[update.message.chat_id]
    try:
        lev = int(update.message.text)
        assert lev>=1 and lev<=125
    except:
        update.message.reply_text("This is not a valid leverage, please enter again.")
        return REALSETLEV
    idx = context.user_data['idx'] 
    user.threads[idx].change_all_leverage(lev)
    return ConversationHandler.END

def set_leverage(update: Update, context: CallbackContext):
    if not update.message.chat_id in CurrentUsers:
        update.message.reply_text("Please initalize with /start first.")
        return ConversationHandler.END
    if CurrentUsers[update.message.chat_id].is_handling:
        update.message.reply_text("You are adding another trader, wait for it to complete first!")
        return ConversationHandler.END
    listtraders = CurrentUsers[update.message.chat_id].trader_names
    if len(listtraders) == 0:
        update.message.reply_text("You are not following any traders.")
        return ConversationHandler.END
    listtraders = split(listtraders,len(listtraders)//2)
    update.message.reply_text("Please choose the trader to set leverage for.\n(/cancel to cancel)",
        reply_markup=ReplyKeyboardMarkup(listtraders,one_time_keyboard=True,input_field_placeholder="Which Trader?")
        )
    return LEVTRADER

def leverage_choosetrader(update: Update, context: CallbackContext):
    user = CurrentUsers[update.message.chat_id]
    logger.info(f"User {user.uname} adjusting leverage.")
    try:
        idx = user.trader_names.index(update.message.text)
    except:
        update.message.reply_text("This is not a valid trader.")
        return ConversationHandler.END
    if not user.threads[idx].toTrade:
        update.message.reply_text("You did not set copy trade option for this trader. If needed, /delete this trader and /add again.")
        return ConversationHandler.END
    context.user_data['idx'] = idx
    UserLocks[update.message.chat_id].acquire()
    listsymbols = user.bclient.get_symbols()
    UserLocks[update.message.chat_id].release()
    listsymbols = [[x] for x in listsymbols]
    update.message.reply_text("Please choose the symbol to set.",reply_markup=ReplyKeyboardMarkup(listsymbols,one_time_keyboard=True,input_field_placeholder="Which Symbol?"))
    return LEVSYM

def leverage_choosesymbol(update: Update, context: CallbackContext):
    user = CurrentUsers[update.message.chat_id]
    context.user_data['symbol'] = update.message.text
    UserLocks[update.message.chat_id].acquire()
    listsymbols = user.bclient.get_symbols()
    UserLocks[update.message.chat_id].release()
    if update.message.text not in listsymbols:
        listsymbols = [[x] for x in listsymbols]
        update.message.reply_text("Sorry, the symbol is not valid, please choose again.",reply_markup=ReplyKeyboardMarkup(listsymbols,one_time_keyboard=True,input_field_placeholder="Which Symbol?"))
        return LEVSYM
    update.message.reply_text("Please enter the target leverage (Integer between 1 and 125)")
    return REALSETLEV2

def setLeverageReal(update: Update, context: CallbackContext):
    user = CurrentUsers[update.message.chat_id]
    try:
        lev = int(update.message.text)
        assert lev>=1 and lev<=125
    except:
        update.message.reply_text("This is not a valid leverage, please enter again.")
        return REALSETLEV
    idx = context.user_data['idx'] 
    symbol = context.user_data['symbol']
    user.threads[idx].change_leverage(symbol,lev)
    return ConversationHandler.END
  
def set_all_proportion(update: Update, context: CallbackContext):
    if not update.message.chat_id in CurrentUsers:
        update.message.reply_text("Please initalize with /start first.")
        return ConversationHandler.END
    if CurrentUsers[update.message.chat_id].is_handling:
        update.message.reply_text("You are adding another trader, wait for it to complete first!")
        return ConversationHandler.END
    listtraders = CurrentUsers[update.message.chat_id].trader_names
    if len(listtraders) == 0:
        update.message.reply_text("You are not following any traders.")
        return ConversationHandler.END
    listtraders = split(listtraders,len(listtraders)//2)
    update.message.reply_text("Please choose the trader to set proportion for all symbols.\n(/cancel to cancel)",
        reply_markup=ReplyKeyboardMarkup(listtraders,one_time_keyboard=True,input_field_placeholder="Which Trader?")
        )
    return ALLPROP

def setAllProportion(update: Update, context: CallbackContext):
    user = CurrentUsers[update.message.chat_id]
    logger.info(f"User {user.uname} adjusting proportion.")
    try:
        idx = user.trader_names.index(update.message.text)
    except:
        update.message.reply_text("This is not a valid trader.")
        return ConversationHandler.END
    if not user.threads[idx].toTrade:
        update.message.reply_text("You did not set copy trade option for this trader. If needed, /delete this trader and /add again.")
        return ConversationHandler.END
    context.user_data['idx'] = idx
    update.message.reply_text("Please enter the target proportion.")
    return REALSETPROP

def setAllProportionReal(update: Update, context: CallbackContext):
    user = CurrentUsers[update.message.chat_id]
    try:
        prop = float(update.message.text)
        assert prop >=0
    except:
        update.message.reply_text("This is not a valid proportion, please enter again.")
        return REALSETPROP
    idx = context.user_data['idx'] 
    user.threads[idx].change_all_proportion(prop)
    return ConversationHandler.END

def set_proportion(update: Update, context: CallbackContext):
    if not update.message.chat_id in CurrentUsers:
        update.message.reply_text("Please initalize with /start first.")
        return ConversationHandler.END
    if CurrentUsers[update.message.chat_id].is_handling:
        update.message.reply_text("You are adding another trader, wait for it to complete first!")
        return ConversationHandler.END
    listtraders = CurrentUsers[update.message.chat_id].trader_names
    if len(listtraders) == 0:
        update.message.reply_text("You are not following any traders.")
        return ConversationHandler.END
    listtraders = split(listtraders,len(listtraders)//2)
    update.message.reply_text("Please choose the trader to set proportion for.\n(/cancel to cancel)",
        reply_markup=ReplyKeyboardMarkup(listtraders,one_time_keyboard=True,input_field_placeholder="Which Trader?")
        )
    return PROPTRADER

def proportion_choosetrader(update: Update, context: CallbackContext):
    user = CurrentUsers[update.message.chat_id]
    logger.info(f"User {user.uname} adjusting proportion.")
    try:
        idx = user.trader_names.index(update.message.text)
    except:
        update.message.reply_text("This is not a valid trader.")
        return ConversationHandler.END
    if not user.threads[idx].toTrade:
        update.message.reply_text("You did not set copy trade option for this trader. If needed, /delete this trader and /add again.")
        return ConversationHandler.END
    context.user_data['idx'] = idx
    UserLocks[update.message.chat_id].acquire()
    listsymbols = user.bclient.get_symbols()
    UserLocks[update.message.chat_id].release()
    listsymbols = [[x] for x in listsymbols]
    update.message.reply_text("Please choose the symbol to set.",reply_markup=ReplyKeyboardMarkup(listsymbols,one_time_keyboard=True,input_field_placeholder="Which Symbol?"))
    return PROPSYM

def proportion_choosesymbol(update: Update, context: CallbackContext):
    user = CurrentUsers[update.message.chat_id]
    context.user_data['symbol'] = update.message.text
    UserLocks[update.message.chat_id].acquire()
    listsymbols = user.bclient.get_symbols()
    UserLocks[update.message.chat_id].release()
    if update.message.text not in listsymbols:
        listsymbols = [[x] for x in listsymbols]
        update.message.reply_text("Sorry, the symbol is not valid, please choose again.",reply_markup=ReplyKeyboardMarkup(listsymbols,one_time_keyboard=True,input_field_placeholder="Which Symbol?"))
        return PROPSYM
    update.message.reply_text("Please enter the target proportion.")
    return REALSETPROP2

def setProportionReal(update: Update, context: CallbackContext):
    user = CurrentUsers[update.message.chat_id]
    try:
        prop = float(update.message.text)
        assert prop >=0
    except:
        update.message.reply_text("This is not a valid proportion, please enter again.")
        return REALSETPROP2
    idx = context.user_data['idx'] 
    symbol = context.user_data['symbol']
    user.threads[idx].change_proportion(symbol,prop)
    return ConversationHandler.END

def get_leverage(update: Update, context: CallbackContext):
    if not update.message.chat_id in CurrentUsers:
        update.message.reply_text("Please initalize with /start first.")
        return ConversationHandler.END
    if CurrentUsers[update.message.chat_id].is_handling:
        update.message.reply_text("You are adding another trader, wait for it to complete first!")
        return ConversationHandler.END
    listtraders = CurrentUsers[update.message.chat_id].trader_names
    if len(listtraders) == 0:
        update.message.reply_text("You are not following any traders.")
        return ConversationHandler.END
    listtraders = split(listtraders,len(listtraders)//2)
    update.message.reply_text("Please choose the trader to query leverage for.\n(/cancel to cancel)",
        reply_markup=ReplyKeyboardMarkup(listtraders,one_time_keyboard=True,input_field_placeholder="Which Trader?")
        )
    return LEVTRADER2

def getleverage_choosetrader(update: Update, context: CallbackContext):
    user = CurrentUsers[update.message.chat_id]
    logger.info(f"User {user.uname} querying leverage.")
    try:
        idx = user.trader_names.index(update.message.text)
    except:
        update.message.reply_text("This is not a valid trader.")
        return ConversationHandler.END
    if not user.threads[idx].toTrade:
        update.message.reply_text("You did not set copy trade option for this trader. If needed, /delete this trader and /add again.")
        return ConversationHandler.END
    context.user_data['idx'] = idx
    UserLocks[update.message.chat_id].acquire()
    listsymbols = user.bclient.get_symbols()
    UserLocks[update.message.chat_id].release()
    listsymbols = [[x] for x in listsymbols]
    update.message.reply_text("Please choose the symbol.",reply_markup=ReplyKeyboardMarkup(listsymbols,one_time_keyboard=True,input_field_placeholder="Which Symbol?"))
    return REALSETLEV3

def getLeverageReal(update: Update, context: CallbackContext):
    user = CurrentUsers[update.message.chat_id]
    symbol = update.message.text
    UserLocks[update.message.chat_id].acquire()
    listsymbols = user.bclient.get_symbols()
    UserLocks[update.message.chat_id].release()
    if symbol not in listsymbols:
        listsymbols = [[x] for x in listsymbols]
        update.message.reply_text("Sorry, the symbol is not valid, please choose again.",reply_markup=ReplyKeyboardMarkup(listsymbols,one_time_keyboard=True,input_field_placeholder="Which Symbol?"))
        return REALSETLEV3
    idx = context.user_data['idx']
    result = user.threads[idx].get_leverage(symbol)
    update.message.reply_text(f"The leverage set for {user.threads[idx].name}, {symbol} is {result}x.")
    return ConversationHandler.END
  
def get_proportion(update: Update, context: CallbackContext):
    if not update.message.chat_id in CurrentUsers:
        update.message.reply_text("Please initalize with /start first.")
        return ConversationHandler.END
    if CurrentUsers[update.message.chat_id].is_handling:
        update.message.reply_text("You are adding another trader, wait for it to complete first!")
        return ConversationHandler.END
    listtraders = CurrentUsers[update.message.chat_id].trader_names
    if len(listtraders) == 0:
        update.message.reply_text("You are not following any traders.")
        return ConversationHandler.END
    listtraders = split(listtraders,len(listtraders)//2)
    update.message.reply_text("Please choose the trader to query proportion for.\n(/cancel to cancel)",
        reply_markup=ReplyKeyboardMarkup(listtraders,one_time_keyboard=True,input_field_placeholder="Which Trader?")
        )
    return LEVTRADER3

def getproportion_choosetrader(update: Update, context: CallbackContext):
    user = CurrentUsers[update.message.chat_id]
    logger.info(f"User {user.uname} querying proportion.")
    try:
        idx = user.trader_names.index(update.message.text)
    except:
        update.message.reply_text("This is not a valid trader.")
        return ConversationHandler.END
    if not user.threads[idx].toTrade:
        update.message.reply_text("You did not set copy trade option for this trader. If needed, /delete this trader and /add again.")
        return ConversationHandler.END
    context.user_data['idx'] = idx
    UserLocks[update.message.chat_id].acquire()
    listsymbols = user.bclient.get_symbols()
    UserLocks[update.message.chat_id].release()
    listsymbols = [[x] for x in listsymbols]
    update.message.reply_text("Please choose the symbol.",reply_markup=ReplyKeyboardMarkup(listsymbols,one_time_keyboard=True,input_field_placeholder="Which Symbol?"))
    return REALSETLEV4

def getproportionReal(update: Update, context: CallbackContext):
    user = CurrentUsers[update.message.chat_id]
    symbol = update.message.text
    UserLocks[update.message.chat_id].acquire()
    listsymbols = user.bclient.get_symbols()
    UserLocks[update.message.chat_id].release()
    if symbol not in listsymbols:
        listsymbols = [[x] for x in listsymbols]
        update.message.reply_text("Sorry, the symbol is not valid, please choose again.",reply_markup=ReplyKeyboardMarkup(listsymbols,one_time_keyboard=True,input_field_placeholder="Which Symbol?"))
        return REALSETLEV4
    idx = context.user_data['idx']
    result = user.threads[idx].get_proportion(symbol)
    update.message.reply_text(f"The proportion set for {user.threads[idx].name}, {symbol} is {result}x.")
    return ConversationHandler.END

def set_omode(update: Update, context: CallbackContext):
    if not update.message.chat_id in CurrentUsers:
        update.message.reply_text("Please initalize with /start first.")
        return ConversationHandler.END
    if CurrentUsers[update.message.chat_id].is_handling:
        update.message.reply_text("You are adding another trader, wait for it to complete first!")
        return ConversationHandler.END
    listtraders = CurrentUsers[update.message.chat_id].trader_names
    if len(listtraders) == 0:
        update.message.reply_text("You are not following any traders.")
        return ConversationHandler.END
    listtraders = split(listtraders,len(listtraders)//2)
    update.message.reply_text("Please choose the trader to set trading mode for.\n(/cancel to cancel)",
        reply_markup=ReplyKeyboardMarkup(listtraders,one_time_keyboard=True,input_field_placeholder="Which Trader?")
        )
    return PROPTRADER2

def omode_choosetrader(update: Update, context: CallbackContext):
    user = CurrentUsers[update.message.chat_id]
    logger.info(f"User {user.uname} adjusting tmode.")
    try:
        idx = user.trader_names.index(update.message.text)
    except:
        update.message.reply_text("This is not a valid trader.")
        return ConversationHandler.END
    if not user.threads[idx].toTrade:
        update.message.reply_text("You did not set copy trade option for this trader. If needed, /delete this trader and /add again.")
        return ConversationHandler.END
    context.user_data['idx'] = idx
    UserLocks[update.message.chat_id].acquire()
    listsymbols = user.bclient.get_symbols()
    UserLocks[update.message.chat_id].release()
    listsymbols = [[x] for x in listsymbols]
    update.message.reply_text("Please choose the symbol to set.",reply_markup=ReplyKeyboardMarkup(listsymbols,one_time_keyboard=True,input_field_placeholder="Which Symbol?"))
    return PROPSYM2

def omode_choosesymbol(update: Update, context: CallbackContext):
    user = CurrentUsers[update.message.chat_id]
    context.user_data['symbol'] = update.message.text
    UserLocks[update.message.chat_id].acquire()
    listsymbols = user.bclient.get_symbols()
    UserLocks[update.message.chat_id].release()
    if update.message.text not in listsymbols:
        listsymbols = [[x] for x in listsymbols]
        update.message.reply_text("Sorry, the symbol is not valid, please choose again.",reply_markup=ReplyKeyboardMarkup(listsymbols,one_time_keyboard=True,input_field_placeholder="Which Symbol?"))
        return PROPSYM2
    update.message.reply_text("Please enter the target trading mode.")
    update.message.reply_text("0. MARKET: Once we detected a change in position, you will make an order immediately at the market price. As a result, your entry price might deviate from the trader's entry price (especially when there are significant market movements).") 
    update.message.reply_text("1. LIMIT: You will make an limit order at the same price as the trader's estimated entry price. However, due to fluctuating market movements, your order might not be fulfilled.")
    update.message.reply_text("2. LIMIT, THEN MARKET: When opening positions, you will make an limit order at the same price as the trader's estimated entry price. When closing positions, you will follow market.")
    update.message.reply_text("Please type 0,1 or 2 to indicate your choice.")
    return REALSETPROP3

def setomodeReal(update: Update, context: CallbackContext):
    user = CurrentUsers[update.message.chat_id]
    try:
        tmode = int(update.message.text)
        assert tmode >=0 and tmode <=2
    except:
        update.message.reply_text("This is not a valid trading mode, please enter again.")
        return REALSETPROP3
    idx = context.user_data['idx'] 
    symbol = context.user_data['symbol']
    user.threads[idx].change_tmode(symbol,tmode)
    return ConversationHandler.END

def set_lmode(update: Update, context: CallbackContext):
    if not update.message.chat_id in CurrentUsers:
        update.message.reply_text("Please initalize with /start first.")
        return ConversationHandler.END
    if CurrentUsers[update.message.chat_id].is_handling:
        update.message.reply_text("You are adding another trader, wait for it to complete first!")
        return ConversationHandler.END
    listtraders = CurrentUsers[update.message.chat_id].trader_names
    if len(listtraders) == 0:
        update.message.reply_text("You are not following any traders.")
        return ConversationHandler.END
    listtraders = split(listtraders,len(listtraders)//2)
    update.message.reply_text("Please choose the trader to set leverage mode for.\n(/cancel to cancel)",
        reply_markup=ReplyKeyboardMarkup(listtraders,one_time_keyboard=True,input_field_placeholder="Which Trader?")
        )
    return LEVTRADER4

def setlmode_choosetrader(update: Update, context: CallbackContext):
    user = CurrentUsers[update.message.chat_id]
    logger.info(f"User {user.uname} setting leverage mode.")
    try:
        idx = user.trader_names.index(update.message.text)
    except:
        update.message.reply_text("This is not a valid trader.")
        return ConversationHandler.END
    if not user.threads[idx].toTrade:
        update.message.reply_text("You did not set copy trade option for this trader. If needed, /delete this trader and /add again.")
        return ConversationHandler.END
    context.user_data['idx'] = idx
    update.message.reply_text("Please choose the leverage mode.")
    update.message.reply_text("0. FOLLOW: You will follow the same leverage as the trader. However, note that the leverage is only an estimate. In case the leverage information cannot be obtained, we would look at the trader's history leverage on the given symbol to determine the leverage. If that was not available as well, a default of 20x leverage would be used.") 
    update.message.reply_text("1. FIXED: You can fix your own leverage settings within this bot for every (trader,symbol) combination. Once we place an order, the leverage set by you will be used regardless of the trader's leverage. Default is 20x and can be changed later.")
    update.message.reply_text("2: IGNORE: You will follow the leverage settings on the binance site, we will not attempt to change any leverage settings for you.")
    update.message.reply_text("Please type 0,1 or 2 to indicate your choice.")
    return REALSETLEV5

def setlmodeReal(update: Update, context: CallbackContext):
    user = CurrentUsers[update.message.chat_id]
    try:
        lmode = int(update.message.text)
        assert lmode >=0 and lmode <=2
    except:
        update.message.reply_text("This is not a valid trading mode, please enter again.")
        return REALSETLEV5
    idx = context.user_data['idx']
    result = user.threads[idx].change_lmode(lmode)
    update.message.reply_text(f"Successfully changed leverage mode!")
    return ConversationHandler.END

def set_allomode(update: Update, context: CallbackContext):
    if not update.message.chat_id in CurrentUsers:
        update.message.reply_text("Please initalize with /start first.")
        return ConversationHandler.END
    if CurrentUsers[update.message.chat_id].is_handling:
        update.message.reply_text("You are adding another trader, wait for it to complete first!")
        return ConversationHandler.END
    listtraders = CurrentUsers[update.message.chat_id].trader_names
    if len(listtraders) == 0:
        update.message.reply_text("You are not following any traders.")
        return ConversationHandler.END
    listtraders = split(listtraders,len(listtraders)//2)
    update.message.reply_text("Please choose the trader to set trading mode for.\n(/cancel to cancel)",
        reply_markup=ReplyKeyboardMarkup(listtraders,one_time_keyboard=True,input_field_placeholder="Which Trader?")
        )
    return LEVTRADER5

def allomode_choosetrader(update: Update, context: CallbackContext):
    user = CurrentUsers[update.message.chat_id]
    logger.info(f"User {user.uname} setting trading mode.")
    try:
        idx = user.trader_names.index(update.message.text)
    except:
        update.message.reply_text("This is not a valid trader.")
        return ConversationHandler.END
    if not user.threads[idx].toTrade:
        update.message.reply_text("You did not set copy trade option for this trader. If needed, /delete this trader and /add again.")
        return ConversationHandler.END
    context.user_data['idx'] = idx
    update.message.reply_text("Please enter the target trading mode.")
    update.message.reply_text("0. MARKET: Once we detected a change in position, you will make an order immediately at the market price. As a result, your entry price might deviate from the trader's entry price (especially when there are significant market movements).") 
    update.message.reply_text("1. LIMIT: You will make an limit order at the same price as the trader's estimated entry price. However, due to fluctuating market movements, your order might not be fulfilled.")
    update.message.reply_text("2. LIMIT, THEN MARKET: When opening positions, you will make an limit order at the same price as the trader's estimated entry price. When closing positions, you will follow market.")
    update.message.reply_text("Please type 0,1 or 2 to indicate your choice.")
    return REALSETLEV6

def setallomodeReal(update: Update, context: CallbackContext):
    user = CurrentUsers[update.message.chat_id]
    try:
        tmode = int(update.message.text)
        assert tmode >=0 and tmode <=2
    except:
        update.message.reply_text("This is not a valid trading mode, please enter again.")
        return REALSETLEV6
    idx = context.user_data['idx']
    user.threads[idx].change_all_tmode(tmode)
    update.message.reply_text(f"Successfully changed trading mode!")
    return ConversationHandler.END
    
def change_safetyratio(update: Update, context: CallbackContext):
    if not update.message.chat_id in CurrentUsers:
        update.message.reply_text("Please initalize with /start first.")
        return ConversationHandler.END
    update.message.reply_text("Please enter the safety ratio (between 0 and 1):")
    return LEVTRADER6

def confirm_changesafety(update: Update, context: CallbackContext):
    try:
        safety_ratio = float(update.message.text)
        assert safety_ratio>=0 and safety_ratio <=1
    except:
        update.message.reply_text("This is not a valid ratio, please enter again.")
        return LEVTRADER6
    UserLocks[update.message.chat_id].acquire()
    CurrentUsers[update.message.chat_id].bclient.change_safety_ratio(safety_ratio)
    UserLocks[update.message.chat_id].release()
    return ConversationHandler.END

def set_all_tpsl(update: Update, context: CallbackContext):
    if not update.message.chat_id in CurrentUsers:
        update.message.reply_text("Please initalize with /start first.")
        return ConversationHandler.END
    if CurrentUsers[update.message.chat_id].is_handling:
        update.message.reply_text("You are adding another trader, wait for it to complete first!")
        return ConversationHandler.END
    listtraders = CurrentUsers[update.message.chat_id].trader_names
    if len(listtraders) == 0:
        update.message.reply_text("You are not following any traders.")
        return ConversationHandler.END
    listtraders = split(listtraders,len(listtraders)//2)
    update.message.reply_text("Please choose the trader to set take profit/stop loss for all symbols.\n(/cancel to cancel)",
        reply_markup=ReplyKeyboardMarkup(listtraders,one_time_keyboard=True,input_field_placeholder="Which Trader?")
        )
    return ALLPROP2

def setAllTpsl(update: Update, context: CallbackContext):
    user = CurrentUsers[update.message.chat_id]
    logger.info(f"User {user.uname} adjusting TPSL.")
    try:
        idx = user.trader_names.index(update.message.text)
    except:
        update.message.reply_text("This is not a valid trader.")
        return ConversationHandler.END
    if not user.threads[idx].toTrade:
        update.message.reply_text("You did not set copy trade option for this trader. If needed, /delete this trader and /add again.")
        return ConversationHandler.END
    context.user_data['idx'] = idx
    update.message.reply_text("Please enter the the target Take profit/stop loss percentage, separated by space.\n(e.g. 200 300 => take profit=200%, stop loss=300%)")
    return REALSETPROP4

def setAllTpslReal(update: Update, context: CallbackContext):
    user = CurrentUsers[update.message.chat_id]
    try:
        ps = update.message.text.split(' ')
        assert len(ps) == 2
        tp = int(ps[0])
        sl = int(ps[1])
        assert tp>=-1 and tp<=400 and sl>=-1 and sl<=400
    except:
        update.message.reply_text("The percentage is invalid, please enter again.")
        return REALSETPROP4
    idx = context.user_data['idx'] 
    user.threads[idx].change_all_tpsl(tp,sl)
    update.message.reply_text("Take profit/stop loss ratio adjusted successfully!!!")
    return ConversationHandler.END

def set_tpsl(update: Update, context: CallbackContext):
    if not update.message.chat_id in CurrentUsers:
        update.message.reply_text("Please initalize with /start first.")
        return ConversationHandler.END
    if CurrentUsers[update.message.chat_id].is_handling:
        update.message.reply_text("You are adding another trader, wait for it to complete first!")
        return ConversationHandler.END
    listtraders = CurrentUsers[update.message.chat_id].trader_names
    if len(listtraders) == 0:
        update.message.reply_text("You are not following any traders.")
        return ConversationHandler.END
    listtraders = split(listtraders,len(listtraders)//2)
    update.message.reply_text("Please choose the trader to set take profit/stop loss percentage for.\n(/cancel to cancel)",
        reply_markup=ReplyKeyboardMarkup(listtraders,one_time_keyboard=True,input_field_placeholder="Which Trader?")
        )
    return PROPTRADER3

def tpsl_choosetrader(update: Update, context: CallbackContext):
    user = CurrentUsers[update.message.chat_id]
    logger.info(f"User {user.uname} adjusting proportion.")
    try:
        idx = user.trader_names.index(update.message.text)
    except:
        update.message.reply_text("This is not a valid trader.")
        return ConversationHandler.END
    if not user.threads[idx].toTrade:
        update.message.reply_text("You did not set copy trade option for this trader. If needed, /delete this trader and /add again.")
        return ConversationHandler.END
    context.user_data['idx'] = idx
    UserLocks[update.message.chat_id].acquire()
    listsymbols = user.bclient.get_symbols()
    UserLocks[update.message.chat_id].release()
    listsymbols = [[x] for x in listsymbols]
    update.message.reply_text("Please choose the symbol to set.",reply_markup=ReplyKeyboardMarkup(listsymbols,one_time_keyboard=True,input_field_placeholder="Which Symbol?"))
    return PROPSYM3

def tpsl_choosesymbol(update: Update, context: CallbackContext):
    user = CurrentUsers[update.message.chat_id]
    context.user_data['symbol'] = update.message.text
    UserLocks[update.message.chat_id].acquire()
    listsymbols = user.bclient.get_symbols()
    UserLocks[update.message.chat_id].release()
    if update.message.text not in listsymbols:
        listsymbols = [[x] for x in listsymbols]
        update.message.reply_text("Sorry, the symbol is not valid, please choose again.",reply_markup=ReplyKeyboardMarkup(listsymbols,one_time_keyboard=True,input_field_placeholder="Which Symbol?"))
        return PROPSYM3
    update.message.reply_text("Please enter the the target Take profit/stop loss percentage, separated by space.\n(e.g. 200 300 => take profit=200%, stop loss=300%)")
    return REALSETPROP5

def setTpslReal(update: Update, context: CallbackContext):
    user = CurrentUsers[update.message.chat_id]
    try:
        ps = update.message.text.split(' ')
        assert len(ps) == 2
        tp = int(ps[0])
        sl = int(ps[1])
        assert tp>=-1 and tp<=400 and sl>=-1 and sl<=400
    except:
        update.message.reply_text("The percentage is invalid, please enter again.")
        return REALSETPROP5
    idx = context.user_data['idx'] 
    symbol = context.user_data['symbol']
    user.threads[idx].change_tpsl(symbol,tp,sl)
    update.message.reply_text("Percentages changed successfully.")
    return ConversationHandler.END

def get_tpsl(update: Update, context: CallbackContext):
    if not update.message.chat_id in CurrentUsers:
        update.message.reply_text("Please initalize with /start first.")
        return ConversationHandler.END
    if CurrentUsers[update.message.chat_id].is_handling:
        update.message.reply_text("You are adding another trader, wait for it to complete first!")
        return ConversationHandler.END
    listtraders = CurrentUsers[update.message.chat_id].trader_names
    if len(listtraders) == 0:
        update.message.reply_text("You are not following any traders.")
        return ConversationHandler.END
    listtraders = split(listtraders,len(listtraders)//2)
    update.message.reply_text("Please choose the trader to query take profit/stop loss percentage for.\n(/cancel to cancel)",
        reply_markup=ReplyKeyboardMarkup(listtraders,one_time_keyboard=True,input_field_placeholder="Which Trader?")
        )
    return LEVTRADER7

def gettpsl_choosetrader(update: Update, context: CallbackContext):
    user = CurrentUsers[update.message.chat_id]
    logger.info(f"User {user.uname} querying tpsl.")
    try:
        idx = user.trader_names.index(update.message.text)
    except:
        update.message.reply_text("This is not a valid trader.")
        return ConversationHandler.END
    if not user.threads[idx].toTrade:
        update.message.reply_text("You did not set copy trade option for this trader. If needed, /delete this trader and /add again.")
        return ConversationHandler.END
    context.user_data['idx'] = idx
    UserLocks[update.message.chat_id].acquire()
    listsymbols = user.bclient.get_symbols()
    UserLocks[update.message.chat_id].release()
    listsymbols = [[x] for x in listsymbols]
    update.message.reply_text("Please choose the symbol.",reply_markup=ReplyKeyboardMarkup(listsymbols,one_time_keyboard=True,input_field_placeholder="Which Symbol?"))
    return REALSETLEV7

def getTpslReal(update: Update, context: CallbackContext):
    user = CurrentUsers[update.message.chat_id]
    symbol = update.message.text
    UserLocks[update.message.chat_id].acquire()
    listsymbols = user.bclient.get_symbols()
    UserLocks[update.message.chat_id].release()
    if symbol not in listsymbols:
        listsymbols = [[x] for x in listsymbols]
        update.message.reply_text("Sorry, the symbol is not valid, please choose again.",reply_markup=ReplyKeyboardMarkup(listsymbols,one_time_keyboard=True,input_field_placeholder="Which Symbol?"))
        return REALSETLEV7
    idx = context.user_data['idx']
    tp,sl = user.threads[idx].get_tpsl(symbol)
    update.message.reply_text(f"The take profit/stop loss percentage set for {user.threads[idx].name}, {symbol} is {tp}% and {sl}% respectively. (-1 means not set)")
    return ConversationHandler.END

class BinanceClient:
    def __init__(self,chat_id,uname,safety_ratio,api_key,api_secret):
        self.client = Client(api_key,api_secret)
        self.chat_id = chat_id
        self.uname = uname
        self.stepsize = {}
        self.ticksize = {}
        self.safety_ratio = safety_ratio
        info = self.client.futures_exchange_info()
        try:
            self.client.futures_change_position_mode(dualSidePosition=True)
        except BinanceAPIException as e:
            logger.error(e)
        for thing in info['symbols']:
            self.ticksize[thing['symbol']] = round(-math.log(float(thing['filters'][0]['tickSize']),10))
            self.stepsize[thing['symbol']] = round(-math.log(float(thing['filters'][1]['stepSize']),10))
        try:
            for symbol in self.ticksize:
                self.client.futures_change_margin_type(symbol=symbol,marginType="CROSSED")
        except BinanceAPIException as e:
            logger.error(e)

    def get_symbols(self):
        symbolList = []
        for symbol in self.stepsize:
            symbolList.append(symbol)
        return symbolList

    def tpsl_trade(self,symbol,side,positionSide,qty,excprice,leverage,tp,sl): #make sure everything in numbers not text//side: original side
        side = "BUY" if side == "SELL" else "SELL"
        logger.info(f"Debug Check {leverage}/{tp}/{sl}")
        if positionSide == "LONG":
            if tp != -1:
                tpPrice1 = excprice * (1+(tp/leverage)/100)
                qty1 = "{:0.0{}f}".format(qty,self.stepsize[symbol])
                tpPrice1 = "{:0.0{}f}".format(tpPrice1,self.ticksize[symbol])
                try:
                    self.client.futures_create_order(symWbol=symbol,side=side,positionSide=positionSide,type="TAKE_PROFIT_MARKET",stopPrice=tpPrice1,workingType="MARK_PRICE",quantity=qty1)
                except BinanceAPIException as e:
                    logger.error(e)
                    updater.bot.sendMessage(chat_id=self.chat_id,text=str(e))
            if sl != -1:
                tpPrice2 = excprice * (1-(sl/leverage)/100)
                qty2 = "{:0.0{}f}".format(qty,self.stepsize[symbol])
                tpPrice2 = "{:0.0{}f}".format(tpPrice2,self.ticksize[symbol])
                try:
                    self.client.futures_create_order(symbol=symbol,side=side,positionSide=positionSide,type="STOP_MARKET",stopPrice=tpPrice2,workingType="MARK_PRICE",quantity=qty2)
                except BinanceAPIException as e:
                    logger.error(e)
                    updater.bot.sendMessage(chat_id=self.chat_id,text=str(e))
        else:
            if tp != -1:
                tpPrice1 = excprice * (1-(tp/leverage)/100)
                qty1 = "{:0.0{}f}".format(qty,self.stepsize[symbol])
                tpPrice1 = "{:0.0{}f}".format(tpPrice1,self.ticksize[symbol])
                try:
                    self.client.futures_create_order(symbol=symbol,side=side,positionSide=positionSide,type="TAKE_PROFIT_MARKET",stopPrice=tpPrice1,workingType="MARK_PRICE",quantity=qty1)
                except BinanceAPIException as e:
                    logger.error(e)
                    updater.bot.sendMessage(chat_id=self.chat_id,text=str(e))
            if sl != -1:
                tpPrice2 = excprice * (1+(sl/leverage)/100)
                qty2 = "{:0.0{}f}".format(qty,self.stepsize[symbol])
                tpPrice2 = "{:0.0{}f}".format(tpPrice2,self.ticksize[symbol])
                try:
                    self.client.futures_create_order(symbol=symbol,side=side,positionSide=positionSide,type="STOP_MARKET",stopPrice=tpPrice2,workingType="MARK_PRICE",quantity=qty2)
                except BinanceAPIException as e:
                    logger.error(e)
                    updater.bot.sendMessage(chat_id=self.chat_id,text=str(e))
        return

    def query_trade(self,orderId,symbol,positionKey,isOpen,uname,takeProfit,stopLoss,Leverage): #ONLY to be run as thread
        numTries = 0
        time.sleep(1)
        result = ""
        executed_qty = 0
        while True: 
            try:
                result = self.client.futures_get_order(symbol=symbol,orderId=orderId)
                if result['status'] == "FILLED":
                    updater.bot.sendMessage(chat_id=self.chat_id,text=f"Order ID {orderId} ({positionKey}) fulfilled successfully.")
                    #ADD TO POSITION
                    if isOpen:
                        idx = CurrentUsers[self.chat_id].trader_names.index(uname)
                        UserLocks[self.chat_id].acquire() #needed bc run as thread
                        if positionKey in CurrentUsers[self.chat_id].threads[idx].positions:
                            CurrentUsers[self.chat_id].threads[idx].positions[positionKey] += float(result['executedQty'])
                        else:
                            CurrentUsers[self.chat_id].threads[idx].positions[positionKey] = float(result['executedQty'])
                        UserLocks[self.chat_id].release()
                        try:
                            self.tpsl_trade(symbol,result['side'],result['positionSide'],float(result['executedQty']),float(result['avgPrice']),Leverage,takeProfit,stopLoss)
                        except:
                            return
                    else:
                        idx = CurrentUsers[self.chat_id].trader_names.index(uname)
                        UserLocks[self.chat_id].acquire() #needed bc run as thread
                        if positionKey in CurrentUsers[self.chat_id].threads[idx].positions:
                            CurrentUsers[self.chat_id].threads[idx].positions[positionKey] -= float(result['executedQty'])
                        else:
                            CurrentUsers[self.chat_id].threads[idx].positions[positionKey] = 0
                        UserLocks[self.chat_id].release()
                    return
                elif result['status'] in ["CANCELED","PENDING_CANCEL","REJECTED","EXPIRED"]:
                    updater.bot.sendMessage(chat_id=self.chat_id,text=f"Order ID {orderId} ({positionKey}) is cancelled/rejected.")
                    return
                elif result['status'] == "PARTIALLY_FILLED":
                    updatedQty = float(result['executedQty']) - executed_qty
                    if isOpen:
                        idx = CurrentUsers[self.chat_id].trader_names.index(uname)
                        UserLocks[self.chat_id].acquire() #needed bc run as thread
                        if positionKey in CurrentUsers[self.chat_id].threads[idx].positions:
                            CurrentUsers[self.chat_id].threads[idx].positions[positionKey] += updatedQty
                        else:
                            CurrentUsers[self.chat_id].threads[idx].positions[positionKey] = updatedQty
                        UserLocks[self.chat_id].release()
                    else:
                        idx = CurrentUsers[self.chat_id].trader_names.index(uname)
                        UserLocks[self.chat_id].acquire() #needed bc run as thread
                        if positionKey in CurrentUsers[self.chat_id].threads[idx].positions:
                            CurrentUsers[self.chat_id].threads[idx].positions[positionKey] -= float(result['executedQty'])
                        else:
                            CurrentUsers[self.chat_id].threads[idx].positions[positionKey] = 0
                        UserLocks[self.chat_id].release()
                    executed_qty = float(result['executedQty'])
            except:
                pass
            if numTries >= 59:
                break
            time.sleep(60)
            numTries += 1
        if result != "" and result['status'] == "PARTIALLY_FILLED":
            updater.bot.sendMessage(chat_id=self.chat_id,text=f"Order ID {orderId} ({positionKey}) is only partially filled. The rest will be cancelled.")
            try:
                self.tpsl_trade(symbol,result['side'],result['positionSide'],float(result['executedQty']),float(result['avgPrice']),Leverage,takeProfit,stopLoss) 
                self.client.futures_cancel_order(symbol=symbol,orderId=orderId)      
            except:
                pass

        if result != "" and result['status'] == "NEW":
            updater.bot.sendMessage(chat_id=self.chat_id,text=f"Order ID {orderId} ({positionKey}) has not been filled. It will be cancelled.")
            try:
                self.client.futures_cancel_order(symbol=symbol,orderId=orderId)      
            except:
                pass

    def open_trade(self,df,uname,proportion,leverage,lmode,tmodes,positions,takeProfit,stopLoss):
        self.reload()
        df = df.values
        allquant = []     
        for tradeinfo in df:
            isOpen = False
            types = tradeinfo[0].upper()
            if types[:4] == "OPEN":
                isOpen = True
                positionSide = types[4:]
                if positionSide == "LONG":
                    side = "BUY"
                else:
                    side = "SELL"
                if lmode != 2:
                    try:
                        self.client.futures_change_leverage(symbol=tradeinfo[1],leverage=leverage[tradeinfo[1]])
                    except:
                        pass
            else:
                positionSide = types[5:]
                if positionSide == "LONG":
                    side = "SELL"
                else:
                    side = "BUY"
            quant = abs(tradeinfo[2]) * proportion[tradeinfo[1]]
            allquant.append(quant)
            checkKey = tradeinfo[1].upper()+positionSide
            if not isOpen and ((checkKey not in positions) or (positions[checkKey] < quant)):
                if checkKey not in positions or positions[checkKey] == 0:
                    updater.bot.sendMessage(chat_id=self.chat_id,text=f"Close {checkKey}: This trade will not be executed because your opened positions with this trader is 0.")
                    continue
                elif positions[checkKey] < quant:
                    quant = min(positions[checkKey],quant)
                    updater.bot.sendMessage(chat_id=self.chat_id,text=f"Close {checkKey}: The trade quantity will be less than expected, because you don't have enough positions to close.")
                    allquant[-1] = quant
            if quant == 0:
                updater.bot.sendMessage(chat_id=self.chat_id,text=f"{side} {checkKey}: This trade will not be executed because size = 0. Adjust proportion if you want to follow.")
                continue
            balance,collateral,coin = 0,0,""
            try:
                coin = "USDT"
                for asset in self.client.futures_account()["assets"]:
                    if asset['asset'] == "USDT":
                        balance = asset['maxWithdrawAmount']
                        break
                if tradeinfo[1][-4:] == "BUSD":
                    tradeinfo[1] = tradeinfo[1][:-4] + "USDT"
                    updater.bot.sendMessage(chat_id=self.chat_id,text="Our system only supports USDT. This trade will be executed in USDT instead of BUSD.")
            except BinanceAPIException as e:
                coin = "USDT"
                balance = "0"
                logger.error(e) 
            balance = float(balance)
            latest_price = float(self.client.futures_mark_price(symbol=tradeinfo[1])['markPrice'])
            collateral = (latest_price * quant) / leverage[tradeinfo[1]]
            if isOpen:
                updater.bot.sendMessage(chat_id=self.chat_id,text=f"For the following trade, you will need {collateral:.3f}{coin} as collateral.")
                if collateral >= balance*self.safety_ratio:
                    updater.bot.sendMessage(chat_id=self.chat_id,text=f"WARNING: this trade will take up more than {self.safety_ratio} of your available balance. It will NOT be executed. Manage your risks accordingly and reduce proportion if necessary.")
                    continue
            reqticksize = self.ticksize[tradeinfo[1]]
            reqstepsize = self.stepsize[tradeinfo[1]]
            quant =  "{:0.0{}f}".format(quant,reqstepsize)
            if isinstance(tradeinfo[3],str):
                tradeinfo[3] = tradeinfo[3].replace(",","")
            target_price = "{:0.0{}f}".format(float(tradeinfo[3]),reqticksize)
            if tmodes[tradeinfo[1]] == 0 or (tmodes[tradeinfo[1]]==2 and not isOpen):
                try:
                    tosend = f"Trying to execute the following trade:\nSymbol: {tradeinfo[1]}\nSide: {side}\npositionSide: {positionSide}\ntype: MARKET\nquantity: {quant}"
                    updater.bot.sendMessage(chat_id=self.chat_id,text=tosend)
                    rvalue = self.client.futures_create_order(symbol=tradeinfo[1],side=side,positionSide=positionSide,type="MARKET",quantity=quant)
                    logger.info(f"{self.uname} opened order.")
                    positionKey = tradeinfo[1] + positionSide
                    t1 = threading.Thread(target=self.query_trade,args=(rvalue['orderId'],tradeinfo[1],positionKey,isOpen,uname,takeProfit[tradeinfo[1]],stopLoss[tradeinfo[1]],leverage[tradeinfo[1]]))
                    t1.start()
                except BinanceAPIException as e:
                    logger.error(e)
                    if not isOpen and str(e).find("2022") >= 0:
                        positionKey = tradeinfo[1] + positionSide
                        idx = CurrentUsers[self.chat_id].trader_names.index(uname)
                        CurrentUsers[self.chat_id].threads[idx].positions[positionKey] = 0
                    updater.bot.sendMessage(chat_id=self.chat_id,text=str(e))
            else:
                try:
                    target_price = float(target_price)
                    if positionSide == "LONG":
                        target_price = min(latest_price,target_price) 
                    else:
                        target_price = max(latest_price,target_price)
                except:
                    pass
                target_price = "{:0.0{}f}".format(float(target_price),reqticksize)
                try:
                    tosend = f"Trying to execute the following trade:\nSymbol: {tradeinfo[1]}\nSide: {side}\npositionSide: {positionSide}\ntype: LIMIT\nquantity: {quant}\nPrice: {target_price}"
                    updater.bot.sendMessage(chat_id=self.chat_id,text=tosend)
                    rvalue = self.client.futures_create_order(symbol=tradeinfo[1],side=side,positionSide=positionSide,type="LIMIT",quantity=quant,price=target_price,timeInForce="GTC")
                    logger.info(f"{self.uname} opened order.")
                    positionKey = tradeinfo[1] + positionSide
                    t1 = threading.Thread(target=self.query_trade,args=(rvalue['orderId'],tradeinfo[1],positionKey,isOpen,uname,takeProfit[tradeinfo[1]],stopLoss[tradeinfo[1]],leverage[tradeinfo[1]]))
                    t1.start()
                except BinanceAPIException as e:
                    logger.error(e)
                    updater.bot.sendMessage(chat_id=self.chat_id,text=str(e))
        return allquant

    def reload(self):
        info = self.client.futures_exchange_info()
        secondticksize = {}
        secondstepsize = {}
        for thing in info['symbols']:
            secondticksize[thing['symbol']] = round(-math.log(float(thing['filters'][0]['tickSize']),10))
            secondstepsize[thing['symbol']] = round(-math.log(float(thing['filters'][1]['stepSize']),10))
        self.ticksize = secondticksize
        self.stepsize = secondstepsize 
    
    def change_safety_ratio(self,safety_ratio):
        logger.info(f"{self.uname} changed safety ratio.")
        self.safety_ratio = safety_ratio
        updater.bot.sendMessage(chat_id=self.chat_id,text="Succesfully changed safety ratio.")
        return

class users:
    def __init__(self,chat_id,uname,safety_ratio,init_trader=None,trader_name=None,api_key=None,api_secret=None,toTrade=None,tp=None,sl=None,tmode=None,lmode=None):
        self.chat_id = chat_id
        self.is_handling = False
        self.uname = uname
        self.api_key = api_key #actually required, but I don't want to change 
        self.threads = []
        self.api_secret = api_secret
        self.bclient = BinanceClient(chat_id,uname,safety_ratio,api_key,api_secret)
        listsymbols = self.bclient.get_symbols()
        if init_trader is None:
            self.trader_urls = []
            self.trader_names = []
            return
        self.trader_urls = [init_trader]
        self.trader_names = [trader_name] 
        if toTrade:
            thr = FetchLatestPosition(listsymbols,init_trader,chat_id,trader_name,uname,toTrade,tp,sl,tmode,lmode) 
        else:
            thr = FetchLatestPosition(listsymbols,init_trader,chat_id,trader_name,uname,toTrade)
        thr.start()
        self.threads.append(thr)

    def add_trader(self,url,name,toTrade,tp=None,sl=None,tmode=None,lmode=None):
        self.trader_urls.append(url)
        self.trader_names.append(name)
        listsymbols = self.bclient.get_symbols()
        if toTrade:
            thr = FetchLatestPosition(listsymbols,url,self.chat_id,name,self.uname,toTrade,tp,sl,tmode,lmode)
        else:
            thr = FetchLatestPosition(listsymbols,url,self.chat_id,name,self.uname,toTrade)
        thr.start()
        self.threads.append(thr)
    
    def restore_trader(self,fetch_url,name,toTrade,tp=-1,sl=-1,tmode=None,lmode=None,proportion=None,leverage=None,positions=None):
        self.trader_urls.append(fetch_url)
        self.trader_names.append(name)
        listSymbols = self.bclient.get_symbols()
        if toTrade:
            thr = FetchLatestPosition(listSymbols,fetch_url,self.chat_id,name,self.uname,toTrade,tp,sl,tmode,lmode,proportion,leverage,positions)
        else:
            thr = FetchLatestPosition(listSymbols,fetch_url,self.chat_id,name,self.uname,toTrade)
        thr.start()
        self.threads.append(thr)

    def delete_trader(self,idx):
        self.trader_urls.pop(idx)
        self.trader_names.pop(idx)
        self.threads[idx].stop()
        self.threads.pop(idx)

def restore_save_data():
    #(self,listSymbols,fetch_url,chat_id,name,uname,toTrade,tp=-1,sl=-1,tmode=None,lmode=None,proportion=None,leverage=None,positions=None):
    #{"chat_id":user.chat_id,"profiles":traderProfiles,"safety_ratrio":user.bclient.safety_ratio,"api_key":user.api_key,"api_secret":user.api_secret})
    with open("userdata.pickle","rb") as f:
        userdata = pickle.load(f)
    for x in userdata:
        UserLocks[x['chat_id']] = threading.Lock()
        CurrentUsers[x['chat_id']] = users(x['chat_id'],x['profiles'][0]['uname'],0,api_key=x['api_key'],api_secret=x['api_secret'])
        for i in range(0,len(x['profiles'])):
            if not x['profiles'][i]['trade']:
                CurrentUsers[x['chat_id']].restore_trader(x['profiles'][i]['url'],x['profiles'][i]['name'],x['profiles'][i]['trade'])
            else:
                CurrentUsers[x['chat_id']].restore_trader(x['profiles'][i]['url'],x['profiles'][i]['name'],x['profiles'][i]['trade'],-1,-1,x['profiles'][i]['tmodes'],x['profiles'][i]['lmode'],x['profiles'][i]['proportion'],x['profiles'][i]['leverage'],x['profiles'][i]['positions'])
    return

def main() -> None:
    """Run the bot."""
    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher

    # Add conversation handler with the states GENDER, PHOTO, LOCATION and BIO
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            AUTH: [MessageHandler(Filters.text & ~Filters.command, auth_check)],
            DISCLAIMER:[MessageHandler(Filters.regex('^(yes)$'),disclaimer_check)],
            APIKEY:[MessageHandler(Filters.text & ~Filters.command, check_api)],
            APISECRET: [MessageHandler(Filters.text & ~Filters.command, check_secret)],
            SAFERATIO: [MessageHandler(Filters.text & ~Filters.command, check_ratio)],
            TRADERURL: [MessageHandler(Filters.text, url_check)],
            TOTRADE: [MessageHandler(Filters.regex('^(yes|no)$'),trade_confirm)],
            TMODE: [MessageHandler(Filters.regex('^(0|1|2)$'),tmode_confirm)],    
            LMODE: [MessageHandler(Filters.regex('^(0|1|2)$'),lmode_confirm)],
            TP: [MessageHandler(Filters.text & ~Filters.command, tp_confirm)],
            SL: [MessageHandler(Filters.text & ~Filters.command, sl_confirm)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    conv_handler2 = ConversationHandler(
        entry_points=[CommandHandler('add', add_trader)],
        states={
            TRADERURL2: [MessageHandler(Filters.text & ~Filters.command, url_add)],
            TOTRADE: [MessageHandler(Filters.regex('^(yes|no)$'),trade_confirm)],
            TMODE: [MessageHandler(Filters.regex('^(0|1|2)$'),tmode_confirm)],    
            LMODE: [MessageHandler(Filters.regex('^(0|1|2)$'),lmode_confirm)],
            TP: [MessageHandler(Filters.text & ~Filters.command, tp_confirm)],
            SL: [MessageHandler(Filters.text & ~Filters.command, sl_confirm)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    conv_handler3 = ConversationHandler(
        entry_points=[CommandHandler('delete',delete_trader)],
        states={
            TRADERNAME:[MessageHandler(Filters.text & ~Filters.command,delTrader)]
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    conv_handler4 = ConversationHandler(
        entry_points=[CommandHandler('admin', admin)],
        states={
            AUTH2: [MessageHandler(Filters.text & ~Filters.command, auth_check2)],
            ANNOUNCE: [
                MessageHandler(Filters.text & ~Filters.command, announce),
                CommandHandler('save',save_to_file),
                CommandHandler('endall',end_everyone)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    conv_handler5 = ConversationHandler(
        entry_points=[CommandHandler("view",view_trader)],
        states={
            VIEWTRADER: [MessageHandler(Filters.text & ~Filters.command, view_traderInfo)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    conv_handler6 = ConversationHandler(
        entry_points=[CommandHandler('setallleverage',set_all_leverage)],
        states={
            ALLLEV:[MessageHandler(Filters.text & ~Filters.command,setAllLeverage)],
            REALSETLEV:[MessageHandler(Filters.text & ~Filters.command,setAllLeverageReal)]
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    conv_handler7 = ConversationHandler(
        entry_points=[CommandHandler('setleverage',set_leverage)],
        states={
            LEVTRADER:[MessageHandler(Filters.text & ~Filters.command,leverage_choosetrader)],
            LEVSYM:[MessageHandler(Filters.text & ~Filters.command,leverage_choosesymbol)],
            REALSETLEV2:[MessageHandler(Filters.text & ~Filters.command,setLeverageReal)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    conv_handler8 = ConversationHandler(
        entry_points=[CommandHandler('setallproportion',set_all_proportion)],
        states={
            ALLPROP:[MessageHandler(Filters.text & ~Filters.command,setAllProportion)],
            REALSETPROP:[MessageHandler(Filters.text & ~Filters.command,setAllProportionReal)]
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    conv_handler9 = ConversationHandler(
        entry_points=[CommandHandler('setproportion',set_proportion)],
        states={
            PROPTRADER:[MessageHandler(Filters.text & ~Filters.command,proportion_choosetrader)],
            PROPSYM:[MessageHandler(Filters.text & ~Filters.command,proportion_choosesymbol)],
            REALSETPROP2:[MessageHandler(Filters.text & ~Filters.command,setProportionReal)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    conv_handler10 = ConversationHandler(
        entry_points=[CommandHandler('getleverage',get_leverage)],
        states={
            LEVTRADER2:[MessageHandler(Filters.text & ~Filters.command,getleverage_choosetrader)],
            REALSETLEV3:[MessageHandler(Filters.text & ~Filters.command,getLeverageReal)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    conv_handler11 = ConversationHandler(
        entry_points=[CommandHandler('getproportion',get_proportion)],
        states={
            LEVTRADER3:[MessageHandler(Filters.text & ~Filters.command,getproportion_choosetrader)],
            REALSETLEV4:[MessageHandler(Filters.text & ~Filters.command,getproportionReal)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    conv_handler12 = ConversationHandler(
        entry_points=[CommandHandler('end',end_all)],
        states={
            COCO:[MessageHandler(Filters.regex('^(yes)$'),realEndAll)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    conv_handler13 = ConversationHandler(
        entry_points=[CommandHandler('settmode',set_omode)],
        states={
            PROPTRADER2:[MessageHandler(Filters.text & ~Filters.command,omode_choosetrader)],
            PROPSYM2:[MessageHandler(Filters.text & ~Filters.command,omode_choosesymbol)],
            REALSETPROP3:[MessageHandler(Filters.regex('^(0|1|2)$'),setomodeReal)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    conv_handler14 = ConversationHandler(
        entry_points=[CommandHandler('setlmode',set_lmode)],
        states={
            LEVTRADER4:[MessageHandler(Filters.text & ~Filters.command,setlmode_choosetrader)],
            REALSETLEV5:[MessageHandler(Filters.regex('^(0|1|2)$'),setlmodeReal)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    conv_handler15 = ConversationHandler(
        entry_points=[CommandHandler('setalltmode',set_allomode)],
        states={
            LEVTRADER5:[MessageHandler(Filters.text & ~Filters.command,allomode_choosetrader)],
            REALSETLEV6:[MessageHandler(Filters.regex('^(0|1|2)$'),setallomodeReal)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    conv_handler16 = ConversationHandler(
        entry_points=[CommandHandler('changesr',change_safetyratio)],
        states={
            LEVTRADER6:[MessageHandler(Filters.text & ~Filters.command,confirm_changesafety)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    conv_handler17 = ConversationHandler(
        entry_points=[CommandHandler('setalltpsl',set_all_tpsl)],
        states={
            ALLPROP2:[MessageHandler(Filters.text & ~Filters.command,setAllTpsl)],
            REALSETPROP4:[MessageHandler(Filters.text & ~Filters.command,setAllTpslReal)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    conv_handler18 = ConversationHandler(
        entry_points=[CommandHandler('settpsl',set_tpsl)],
        states={
            PROPTRADER3:[MessageHandler(Filters.text & ~Filters.command,tpsl_choosetrader)],
            PROPSYM3:[MessageHandler(Filters.text & ~Filters.command,tpsl_choosesymbol)],
            REALSETPROP5:[MessageHandler(Filters.text & ~Filters.command,setTpslReal)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    conv_handler19 = ConversationHandler(
        entry_points=[CommandHandler('gettpsl',get_tpsl)],
        states={
            LEVTRADER7:[MessageHandler(Filters.text & ~Filters.command,gettpsl_choosetrader)],
            REALSETLEV7:[MessageHandler(Filters.text & ~Filters.command,getTpslReal)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )    
    
    dispatcher.add_handler(conv_handler)
    dispatcher.add_handler(conv_handler2)
    dispatcher.add_handler(conv_handler3)
    dispatcher.add_handler(conv_handler4)
    dispatcher.add_handler(conv_handler5)
    dispatcher.add_handler(conv_handler6)
    dispatcher.add_handler(conv_handler7)
    dispatcher.add_handler(conv_handler8)
    dispatcher.add_handler(conv_handler9)
    dispatcher.add_handler(conv_handler10)
    dispatcher.add_handler(conv_handler11)
    dispatcher.add_handler(conv_handler12)
    dispatcher.add_handler(conv_handler13)
    dispatcher.add_handler(conv_handler14)
    dispatcher.add_handler(conv_handler15)
    dispatcher.add_handler(conv_handler16)
    dispatcher.add_handler(conv_handler17)
    dispatcher.add_handler(conv_handler18)
    dispatcher.add_handler(conv_handler19)
    dispatcher.add_handler(CommandHandler("help", help_command))
    #TODO: add /end command
    # Start the Bot
    #chat_id,uname,safety_ratio,init_trader,trader_name,api_key,api_secret,toTrade,tmode=None,lmode=None)
    #(self,url,name,toTrade,tmode=None,lmode=None):
    #save_items.append({"chat_id":user.chat_id,"profiles":traderProfiles,"api_key":user.api_key,"api_secret":user.api_secret})
    #{"url":self.fetch_url,"name":self.name,"uname":self.uname,"trade":self.toTrade,"tmodes":self.tmodes,"lmode":self.lmode,"proportion":self.proportion,"leverage":self.leverage,"positions":self.positions}
    #chat_id,uname,safety_ratio,init_trader,trader_name,api_key,api_secret,toTrade,tp=None,sl=None,tmode=None,lmode=None):
     # for x in userdata:
    #     updater.bot.sendMessage(chat_id=x["chat_id"],text="Hi, back online again. You should start receiving notifications now. Remember to change necessary settings.")
    restore_save_data()
    t1 = threading.Thread(target=automatic_reload)
    t1.start()

    updater.start_polling()
    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()

if __name__ == '__main__':
    main()