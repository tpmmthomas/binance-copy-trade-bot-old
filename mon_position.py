from telegram.message import Message
import constants as cnt
import logging

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
import queue


# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

logger = logging.getLogger(__name__)

AUTH, TRADERURL, TRADERURL2, TRADERNAME = range(4)
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
                    mutex.acquire()
                    tosend = f"Trader {self.name}, Current time: "+str(now)+"\nNo positions.\n"
                    with open(cfg.save_file,"a",encoding='utf-8') as f:
                        f.write(tosend)
                    updater.bot.sendMessage(chat_id=self.chat_id,text=tosend)
                    mutex.release()
                    # SEE THIS TWO TIMES BEFORE DOING ANYTHING
                if self.num_no_data != 1:
                    self.prev_df = "x"
                    time.sleep(40)
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
                mutex.acquire()
                tosend = f"Trader {self.name}, Current time: "+str(now)+"\n"+output["time"]+"\n"+output["data"].to_string()+"\n"
                with open(cfg.save_file,"a",encoding='utf-8') as f:
                    f.write(tosend)
                updater.bot.sendMessage(chat_id=self.chat_id,text=tosend)
                mutex.release()
            self.prev_df = output["data"][["symbol","size","Entry Price"]]
            time.sleep(50)
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
    while not success:
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
        'Welcome! Before you start, please type in the access code (6 digits).'
    )
    return AUTH

def auth_check(update: Update, context: CallbackContext) -> int:
    user = update.message.from_user
    logger.info("%s is doing authentication check.", user.first_name)
    if update.message.text == cnt.auth_code:
        update.message.reply_text(
            'Great! Please provide a full URL to the trader you want to follow.'
        )
        return TRADERURL
    else:
        update.message.reply_text("Sorry! The access code is wrong. Type /start again if you need to retry.")
        return ConversationHandler.END


def url_check(update: Update, context: CallbackContext) -> int:
    context.user_data['url'] = update.message.text
    try:
        myDriver = webdriver.Chrome(cfg.driver_location,options=options)
        myDriver.get(context.user_data['url'])
    except:
        update.message.reply_text("Sorry! Your URL is invalid. Please try entering again.")
        return TRADERURL
    myDriver.quit()
    traderName = retrieveUserName(context.user_data['url'])
    user = update.message.from_user
    logger.info("%s has entered the first url.", user.first_name)
    update.message.reply_text(
        f'Thanks! You will start receiving alerts when {traderName} changes positions.\nType /help to view a list of available commands.', reply_markup=ReplyKeyboardRemove()
    )
    CurrentUsers[update.message.chat_id] = users(update.message.chat_id,context.user_data['url'],traderName)
    
    return ConversationHandler.END

def cancel(update: Update, context: CallbackContext) -> int:
    """Cancels and ends the conversation."""
    user = update.message.from_user
    logger.info("User %s canceled the conversation.", user.first_name)
    update.message.reply_text(
        'Operation canceled.', reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

def add_trader(update: Update, context: CallbackContext) -> int:
    if not update.message.chat_id in CurrentUsers:
        update.message.reply_text("Please initalize with /start first.")
        return ConversationHandler.END
    update.message.reply_text(
        'Please enter full URL of the trader you want to add.'
    )
    return TRADERURL2

def url_add(update: Update, context: CallbackContext) -> int:
    context.user_data['url'] = update.message.text  
    try:
        myDriver = webdriver.Chrome(cfg.driver_location,options=options)
        myDriver.get(context.user_data['url'])
    except:
        update.message.reply_text("Sorry! Your URL is invalid. Please try entering again.")
        return TRADERURL2
    myDriver.quit()
    traderName = retrieveUserName(context.user_data['url'])
    if traderName in CurrentUsers[update.message.chat_id].trader_names:
        update.message.reply_text("You already followed this trader.")
        return ConversationHandler.END
    user = update.message.from_user
    logger.info("%s has entered the url.", user.first_name)
    update.message.reply_text(
        f'Thanks! You will start receiving alerts when {traderName} changes positions.', reply_markup=ReplyKeyboardRemove()
    )
    CurrentUsers[update.message.chat_id].add_trader(context.user_data['url'],traderName)
    
    return ConversationHandler.END

def help_command(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /help is issued."""
    update.message.reply_text('/start: Initalize and begin following traders\n/add: add a trader\n/delete: remove a trader')

def delete(update: Update, context: CallbackContext):
    listtraders = CurrentUsers[update.message.chat_id].trader_names
    if len(listtraders[0]) == 0:
        update.message.reply_text("You are not following any traders.")
        return ConversationHandler.END
    update.message.reply_text("Please choose the trader to remove.\n(/cancel to cancel)",
        reply_markup=ReplyKeyboardMarkup(listtraders,one_time_keyboard=True,input_field_placeholder="Which Trader?")
        )
    return TRADERNAME

def delTrader(update: Update, context: CallbackContext):
    user = CurrentUsers[update.message.chat_id]
    try:
        idx = user.trader_names.index(update.message.text)
    except:
        update.message.reply_text("This is not a valid trader.")
        return ConversationHandler.END
    update.message.reply_text("Please wait...")
    user.trader_urls.pop(idx)
    user.trader_names.pop(idx)
    user.threads[idx].stop()
    user.threads.pop(idx)
    #update.message.reply_text(f"Successfully removed {update.message.text}.")
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
            TRADERURL: [MessageHandler(Filters.text, url_check)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    conv_handler2 = ConversationHandler(
        entry_points=[CommandHandler('add', add_trader)],
        states={
            TRADERURL2: [MessageHandler(Filters.text, url_add)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    conv_handler3 = ConversationHandler(
        entry_points=[CommandHandler('delete',delete)],
        states={
            TRADERNAME:[MessageHandler(Filters.text & ~Filters.command,delTrader)]
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    dispatcher.add_handler(conv_handler)
    dispatcher.add_handler(conv_handler2)
    dispatcher.add_handler(conv_handler3)
    dispatcher.add_handler(CommandHandler("help", help_command))

    #TODO: add /end command
    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == '__main__':
    main()