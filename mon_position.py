from telegram.message import Message
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
import queue

import urllib3
urllib3.disable_warnings()
# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

logger = logging.getLogger(__name__)

AUTH, TRADERURL, TRADERURL2, TRADERNAME, AUTH2, ANNOUNCE,DISCLAIMER = range(7)
CurrentUsers = {}
updater = Updater(cnt.bot_token)
mutex = threading.Lock()
options = webdriver.ChromeOptions()
options.binary_location = cfg.chrome_location
options.add_argument("--headless")
options.add_argument("--disable-web-security")

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
    def __init__(self,fetch_url,chat_id,name):
        threading.Thread.__init__(self)
        self.prev_df = None
        self.isStop = threading.Event()
        self.fetch_url = fetch_url
        self.num_no_data = 0
        self.chat_id = chat_id
        self.name = name
        while True:
            try:
                self.driver = webdriver.Chrome(cfg.driver_location,options=options)
                break
            except: 
                time.sleep(0.1)
                continue
        self.first_run = True

    def changes(self,df,df2):
        txtype = []
        txsymbol = []
        txsize = []
        if isinstance(df,str):
            for index,row in df2.iterrows():
                size = row['size']
                if isinstance(size,str):
                    size = size.replace(",","")
                size = float(size)
                if size >0:
                    txtype.append("BuyLong")
                    txsymbol.append(row['symbol'])
                    txsize.append(size)
                else:
                    txtype.append("BuyShort")
                    txsymbol.append(row['symbol'])
                    txsize.append(size)
            txs = pd.DataFrame({"txtype":txtype,"symbol":txsymbol,"size":txsize})
        elif isinstance(df2,str):
            for index,row in df.iterrows():
                size = row['size']  
                if isinstance(size,str):
                    size = size.replace(",","")
                size = float(size)
                if size > 0:
                    txtype.append("SellLong")
                    txsymbol.append(row['symbol'])
                    txsize.append(-size)
                else:
                    txtype.append("SellShort")
                    txsymbol.append(row['symbol'])
                    txsize.append(-size)
            txs = pd.DataFrame({"txtype":txtype,"symbol":txsymbol,"size":txsize})
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
                isPositive = size >=0
                for r in idx:
                    df2row = df2.loc[r].values
                    newsize = df2row[1]
                    if isinstance(newsize,str):
                        newsize = newsize.replace(",","")
                    newsize = float(newsize)
                    if newsize == size:
                        df2 = df2.drop(r)
                        hasChanged = True
                        break
                    if isPositive and newsize > 0:
                        changesize = newsize-size
                        if changesize > 0:
                            txtype.append("BuyLong")
                            txsymbol.append(df2row[0])
                            txsize.append(changesize)
                        else:
                            txtype.append("SellLong")
                            txsymbol.append(df2row[0])
                            txsize.append(changesize)
                        df2 = df2.drop(idx)
                        hasChanged = True
                        break
                    if not isPositive and newsize < 0:
                        changesize = newsize - size
                        if changesize > 0:
                            txtype.append("SellShort")
                            txsymbol.append(df2row[0])
                            txsize.append(changesize)
                        else:
                            txtype.append("BuyShort")
                            txsymbol.append(df2row[0])
                            txsize.append(changesize)
                        df2 = df2.drop(r)
                        hasChanged = True
                        break
                if not hasChanged:
                    if size > 0:
                        txtype.append("SellLong")
                        txsymbol.append(row['symbol'])
                        txsize.append(-size)
                    else:
                        txtype.append("SellShort")
                        txsymbol.append(row['symbol'])
                        txsize.append(-size)
            for index,row in df2.iterrows():
                size = row['size']  
                if isinstance(size,str):
                    size = size.replace(",","")
                size = float(size)
                if size >0:
                    txtype.append("BuyLong")
                    txsymbol.append(row['symbol'])
                    txsize.append(size)
                else:
                    txtype.append("BuyShort")
                    txsymbol.append(row['symbol'])
                    txsize.append(size)
            txs = pd.DataFrame({"txType":txtype,"symbol":txsymbol,"size":txsize})
        tosend = "*The following transactions will be executed:*\n"+txs.to_string()+"\n"
        updater.bot.sendMessage(chat_id=self.chat_id,text=tosend,parse_mode=telegram.ParseMode.MARKDOWN)
    def run(self):
        print("starting",self.name)
        while not self.isStop.is_set():
            isChanged = False
            try:
                self.driver.get(self.fetch_url)
            except:
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
                        self.changes(self.prev_df,"x")
                if self.num_no_data != 1:
                    self.prev_df = "x"
                    time.sleep(60)
                time.sleep(5)
                continue
            else:
                self.num_no_data = 0
            #######################################################################
            try:
                output = format_results(x,self.driver.page_source)
            except:
                continue
            if output["data"].empty:
                continue
            if self.prev_df is None or isinstance(self.prev_df,str):
                isChanged = True
            else:
                try:
                    toComp = output["data"][["symbol","size","Entry Price"]]
                    prevdf = self.prev_df[["symbol","size","Entry Price"]]
                except:
                    continue
                if not toComp.equals(prevdf):
                    isChanged=True
            if isChanged:
                now = datetime.now()
                tosend = f"Trader {self.name}, Current time: "+str(now)+"\n"+output["time"]+"\n"+output["data"].to_string()+"\n"
                updater.bot.sendMessage(chat_id=self.chat_id,text=tosend)
                if not self.first_run:
                    self.changes(self.prev_df,output["data"])
            self.prev_df = output["data"]
            self.first_run = False
            time.sleep(60)
        self.driver.quit()
        updater.bot.sendMessage(chat_id=self.chat_id,text=f"Successfully quit following trader {self.name}.")
    def stop(self):
        self.isStop.set()

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
        '*Welcome!* Before you start, please type in the access code (6 digits).',
        parse_mode=telegram.ParseMode.MARKDOWN
    )
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
    update.message.reply_text("Please provide a full URL to the trader you want to follow.")
    return TRADERURL

def initTraderThread(url,chat_id):
    traderName = retrieveUserName(url)
    CurrentUsers[chat_id] = users(chat_id,url,traderName)
    updater.bot.sendMessage(
        chat_id = chat_id,
        text=f'Thanks! You will start receiving alerts when {traderName} changes positions.\nType /help to view a list of available commands.'
    )

def url_check(update: Update, context: CallbackContext) -> int:
    url = update.message.text
    user = update.message.from_user
    update.message.reply_text("Please wait...")
    logger.info("%s has entered the first url.", update.message.from_user.first_name)
    try:
        a = url.find(".com")
        b = url.find("fut")
        url = url[:a+5] + "en" + url[b-1:]
        myDriver = webdriver.Chrome(cfg.driver_location,options=options)
        myDriver.get(url)
    except:
        update.message.reply_text("Sorry! Your URL is invalid. Please try entering again.")
        return TRADERURL
    myDriver.quit()
    t1 = threading.Thread(target=initTraderThread,args=(url,update.message.chat_id))
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
    update.message.reply_text(
        'Please enter full URL of the trader you want to add.'
    )
    return TRADERURL2

def addTraderThread(url,chat_id,firstname):
    traderName = retrieveUserName(url)
    if traderName in CurrentUsers[chat_id].trader_names:
        print(traderName,CurrentUsers[chat_id].trader_names)
        updater.bot.sendMessage(chat_id=chat_id,text="You already followed this trader.")
        mutex.acquire()
        CurrentUsers[chat_id].is_handling = False
        mutex.release()
        return
    logger.info("%s has added trader %s.", firstname,traderName)
    updater.bot.sendMessage(
        chat_id = chat_id,
        text=f'Thanks! You will start receiving alerts when {traderName} changes positions.'
    )
    CurrentUsers[chat_id].add_trader(url,traderName)
    mutex.acquire()
    CurrentUsers[chat_id].is_handling = False
    mutex.release()

def url_add(update: Update, context: CallbackContext) -> int:
    url = update.message.text
    update.message.reply_text("Please wait...", reply_markup=ReplyKeyboardRemove())
    try:
        a = url.find(".com")
        b = url.find("fut")
        url = url[:a+5] + "en" + url[b-1:]
        myDriver = webdriver.Chrome(cfg.driver_location,options=options)
        myDriver.get(url)
    except:
        update.message.reply_text("Sorry! Your URL is invalid. Please try entering again.")
        return TRADERURL2
    myDriver.quit()
    mutex.acquire()
    CurrentUsers[update.message.chat_id].is_handling = True
    mutex.release()
    t1 = threading.Thread(target=addTraderThread,args=(url,update.message.chat_id,update.message.from_user.first_name))
    t1.start()
    return ConversationHandler.END

def help_command(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /help is issued."""
    update.message.reply_text('/start: Initalize and begin following traders\n/add: add a trader\n/delete: remove a trader\n/admin: Announce message to all users (need authorization code)\n/end: End the service.')

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


def delTrader(update: Update, context: CallbackContext):
    user = CurrentUsers[update.message.chat_id]
    logger.info("%s deleting trader//.",update.message.text)
    try:
        idx = user.trader_names.index(update.message.text)
    except:
        update.message.reply_text("This is not a valid trader.")
        return ConversationHandler.END
    update.message.reply_text("Please wait. It takes around 1 min...")
    user.trader_urls.pop(idx)
    user.trader_names.pop(idx)
    user.threads[idx].stop()
    user.threads.pop(idx)
    #update.message.reply_text(f"Successfully removed {update.message.text}.")
    return ConversationHandler.END

def end_all(update:Update, context: CallbackContext):
    if not update.message.chat_id in CurrentUsers:
        update.message.reply_text("Please initalize with /start first.")
        return
    if CurrentUsers[update.message.chat_id].is_handling:
        update.message.reply_text("You are adding another trader, wait for it to complete first!")
        return
    user = CurrentUsers[update.message.chat_id]
    for thread in user.threads:
        thread.stop()
    del CurrentUsers[update.message.chat_id]
    logger.info("%s ended the service.",update.message.from_user.first_name)
    update.message.reply_text("Sorry to see you go. You are welcome to set up service again with /start.")

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
        save_items.append({"chat_id":user.chat_id,"urls":user.trader_urls})
    with open("userdata.pickle",'wb') as f:
        pickle.dump(save_items,f)
    logger.info("Saved user current state.")
    return ConversationHandler.END


    
class users:
    def __init__(self,chat_id,init_trader,trader_name):#,init_proportion,api_key,api_secret):
        self.chat_id = chat_id
        self.trader_urls = [init_trader]
        self.trader_names = [trader_name] #(do later)
        #self.trade_proportions = [init_proportion]
        #self.trade_masks = [[]] #do later
        #self.api_key = api_key
        #self.api_secret = api_secret
        self.threads = []
        self.is_handling = False
        thr = FetchLatestPosition(init_trader,chat_id,trader_name) 
        thr.start()
        self.threads.append(thr)
    def add_trader(self,url,name):
        self.trader_urls.append(url)
        self.trader_names.append(name)
        thr = FetchLatestPosition(url,self.chat_id,name)
        thr.start()
        self.threads.append(thr)
    #def remove_trader
    #def edit_trader

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
            TRADERURL: [MessageHandler(Filters.text, url_check)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    conv_handler2 = ConversationHandler(
        entry_points=[CommandHandler('add', add_trader)],
        states={
            TRADERURL2: [MessageHandler(Filters.text & ~Filters.command, url_add)],
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

    dispatcher.add_handler(conv_handler)
    dispatcher.add_handler(conv_handler2)
    dispatcher.add_handler(conv_handler3)
    dispatcher.add_handler(conv_handler4)
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(CommandHandler("end",end_all))
    #TODO: add /end command
    # Start the Bot
    
    
    with open("userdata.pickle","rb") as f:
        userdata = pickle.load(f)
    for x in userdata:
        tname = retrieveUserName(x["urls"][0])
        CurrentUsers[x["chat_id"]] = users(x["chat_id"],x["urls"][0],tname)
        for turl in x["urls"][1:]:
            tname = retrieveUserName(turl)
            CurrentUsers[x["chat_id"]].add_trader(turl,tname)
            time.sleep(10)

    updater.start_polling()
    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == '__main__':
    main()