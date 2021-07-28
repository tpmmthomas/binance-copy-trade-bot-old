import os
from telegram import chat
import constants as cnt
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException
from time import sleep
import binance
import pandas as pd
import datetime
import threading
import time
import logging
import math
import queue
import pickle
from unicorn_binance_websocket_api.unicorn_binance_websocket_api_manager import BinanceWebSocketApiManager
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
import json
q = queue.Queue(200)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
AUTH, COCO,TRADERURL,MUTE1,MUTE2,ALLPROP2,REALSETPROP4,LEVTRADER6,LEVTRADER7,REALSETLEV7,LEVTRADER3,REALSETLEV4,LEVTRADER4,REALSETLEV5,LEVTRADER5,REALSETLEV6, TRADERURL2, LEVTRADER2,REALSETLEV3,TRADERNAME, AUTH2, ANNOUNCE,DISCLAIMER,VIEWTRADER,TP,SL,TOTRADE,TMODE,LMODE,APIKEY,APISECRET,ALLLEV,REALSETLEV,LEVTRADER,LEVSYM,REALSETLEV2,ALLPROP,REALSETPROP,PROPTRADER,PROPSYM,REALSETPROP2,PROPTRADER3,PROPSYM3,REALSETPROP5,PROPTRADER2,PROPSYM2,REALSETPROP3,SAFERATIO= range(48)

logger = logging.getLogger(__name__)

updater = Updater(cnt.bot_token2)

current_users = {}
current_stream = None

class getStreamData(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.socket = BinanceWebSocketApiManager(exchange="binance.com-futures")
        self.socket.create_stream(["arr"],["!userData"],api_key=cnt.api_key,api_secret=cnt.api_secret)
        self.isStop = threading.Event()
        self.client = Client(cnt.api_key,cnt.api_secret)

    def run(self):
        time.sleep(2)
        while not self.isStop.is_set():
            if self.socket.is_manager_stopping():
                exit(0)
            buffer = self.socket.pop_stream_data_from_stream_buffer()
            if buffer is False:
                time.sleep(5)
            else:
                buffer = json.loads(buffer)
                if buffer["e"] == "ORDER_TRADE_UPDATE":
                    if  buffer["o"]["X"] == "FILLED":
                        while q.full():
                            time.sleep(1)
                        q.put(buffer)
                logger.info(str(buffer))

    def stop(self):
        self.isStop.set()
    
    def get_positions(self):
        result = self.client.futures_position_information()
        symbol = []
        size = []
        EnPrice = []
        MarkPrice = []
        PNL = []
        margin = []
        for pos in result:
            if float(pos['positionAmt']) != 0:
                symbol.append(pos['symbol'])
                tsize = pos['positionAmt'] if pos['positionSide'] == "LONG" else "-"+pos['positionAmt']
                size.append(tsize)
                EnPrice.append(pos['entryPrice'])
                MarkPrice.append(pos['markPrice'])
                PNL.append(pos['unRealizedProfit'])
                margin.append(pos['leverage'])
                for user in current_users:
                    if current_users[user].lmode == 0:
                        user.leverage[pos['symbol']] = pos['leverage']
        if len(symbol) > 0:
            return pd.DataFrame({'symbol':symbol,'size':size,"Entry Price":EnPrice,"Mark Price":MarkPrice,"PNL":PNL,"leverage":margin}).to_string()
        return "No Positions."

def get_newest_trade():
    global current_stream
    time.sleep(10)
    while True:
        while q.empty():
            time.sleep(1)
        result = q.get()
        result = result["o"]
        symbol = result["s"]
        side = result["S"]
        qty = result["l"]
        type = result["o"]
        positionSide = result["ps"]
        if positionSide == "LONG":
            side = "OpenLong" if side == "BUY" else "CloseLong"
        else:
            side = "OpenShort" if side == "SELL" else "CloseShort"
        price = result["ap"]
        pos = current_stream.get_positions()
        for chat_id in current_users:
            updater.bot.sendMessage(chat_id=chat_id,text=f"The updated position:\n{pos}")
            updater.bot.sendMessage(chat_id=chat_id,text=f"The following trade is executed:\nSymbol: {symbol}\nType: {type}\nside: {side}\nExcPrice: {price}\nQuantity: {qty}")
            current_users[chat_id].open_trade(result)

def automatic_reload():
    global current_stream
    while True:
        time.sleep(23*60*60)
        current_stream.stop()
        newStream = getStreamData()
        newStream.start()
        current_stream = newStream

def start(update: Update, context: CallbackContext) -> int:
    if update.message.chat_id in current_users:
        update.message.reply_text("You have already initalized! Please use other commands, or use /end to end current session before initializing another.")
        return ConversationHandler.END
    update.message.reply_text(
        f"*Welcome {update.message.from_user.first_name}! Note that this bot is only for following Kevin's account.* Before you start, please type in the access code (6 digits).",
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
    update.message.reply_text("You have successfully initialized :)")
    context.user_data['sl'] = sl
    current_users[update.message.chat_id] = userClient(update.message.chat_id,context.user_data['uname'],context.user_data['safe_ratio'],context.user_data['api_key'],context.user_data['api_secret'],context.user_data['tp'],context.user_data['sl'],context.user_data['tmode'],context.user_data['lmode'])
    return ConversationHandler.END    
    
def help_command(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /help is issued."""
    update.message.reply_text('***GENERAL***\n/start: Initalize and begin following traders\n/admin: Announce message to all users (need authorization code)\n/help: view list of commands\n/view : view the current positions.\n/mute: Mute all notifications of trader (except sucessfully fulfilled trades)\n/unmute: Get notifications of trader\n/end: End the service.\n***TRADE COPY CONFIG***\n/setproportion: Set the trade copy proportion for a (trader,symbol) pair.\n/setallproportion: Set the trade copy proportion for a trader, all symbols.\n/getproportion: Get the current proportion for a (trader,symbol) pair\n/setleverage: set leverage for a (trader,symbol) pair.\n/setallleverage: set leverage for a trader, all symbols.\n/getleverage: Get the current leverage for the (trader,symbol) pair.\n/setlmode: Change the leverage mode of a trader.\n/settmode: Change the trading mode for a (trader,symbol) pair.\n/setalltmode: Change trading mode for a trader, all symbols.\n/changesr: Change safety ratio\n/gettpsl: Get the take profit/stop loss ratio of a (trader,symbol) pair.\n/settpsl: Set the take profit/stop loss ratio of a (trader,symbol) pair.\n/setalltpsl: Set the take profit/stop loss ratio of a trader, all symbols.')

def end(update: Update, context: CallbackContext):
    if not update.message.chat_id in current_users:
        update.message.reply_text("You have already initialized. No need to do it again.")
        return
    update.message.reply_text("Bye!")
    current_users.remove(update.message.chat_id)

def cancel(update: Update, context: CallbackContext) -> int:
    """Cancels and ends the conversation."""
    user = update.message.from_user
    logger.info("User %s canceled the conversation.", update.message.from_user.first_name)
    update.message.reply_text(
        'Operation canceled.', reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

def end_everyone(update:Update, context: CallbackContext):
    for user in current_users:
        updater.bot.sendMessage(chat_id=user,text="Your service has been force ended by admin.")
    current_users = {}
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
    for user in current_users:
        updater.bot.sendMessage(chat_id=user,text=update.message.text)
    logger.info("Message announced for all users.")
    return ConversationHandler.END

def save_to_file(update: Update, context: CallbackContext):
    save_items = []
    for user in current_users:
        user = current_users[user]
        save_items.append({"chat_id":user.chat_id,"safety_ratio":user.safety_ratio,"api_key":user.api_key,"api_secret":user.api_secret,"tp":user.tp,"sl":user.sl,"tmode":user.tmode,"lmode":user.lmode,"positions":user.positions,"proportion":user.proportion,"leverage":user.leverage})
    with open("userdata_calvin.pickle",'wb') as f:
        pickle.dump(save_items,f)
    logger.info("Saved user current state.")
    return ConversationHandler.END

def view_position(update:Update,context:CallbackContext):
    global current_stream
    txt = current_stream.get_positions()
    logger.info(f"Debug: {txt}")
    updater.bot.sendMessage(chat_id=update.message.chat_id,text=txt)
    return

def setAllLeverage(update: Update, context: CallbackContext):
    if not update.message.chat_id in current_users:
        update.message.reply_text("Please initalize with /start first.")
        return ConversationHandler.END
    user = current_users[update.message.chat_id]
    logger.info(f"User {user.uname} adjusting leverage.")
    update.message.reply_text("Please enter the target leverage (Integer between 1 and 125)")
    return REALSETLEV

def setAllLeverageReal(update: Update, context: CallbackContext):
    user = current_users[update.message.chat_id]
    try:
        lev = int(update.message.text)
        assert lev>=1 and lev<=125
    except:
        update.message.reply_text("This is not a valid leverage, please enter again.")
        return REALSETLEV
    user.change_all_leverage(lev)
    return ConversationHandler.END

def set_leverage(update: Update, context: CallbackContext):
    if not update.message.chat_id in current_users:
        update.message.reply_text("Please initalize with /start first.")
        return ConversationHandler.END
    listsymbols = current_users[update.message.chat_id].get_symbols()
    listsymbols = [[x] for x in listsymbols]
    update.message.reply_text("Please choose the symbol to set.",reply_markup=ReplyKeyboardMarkup(listsymbols,one_time_keyboard=True,input_field_placeholder="Which Symbol?"))
    return LEVTRADER

def leverage_choosesymbol(update: Update, context: CallbackContext):
    user = current_users[update.message.chat_id]
    context.user_data['symbol'] = update.message.text
    listsymbols = user.get_symbols()
    if update.message.text not in listsymbols:
        listsymbols = [[x] for x in listsymbols]
        update.message.reply_text("Sorry, the symbol is not valid, please choose again.",reply_markup=ReplyKeyboardMarkup(listsymbols,one_time_keyboard=True,input_field_placeholder="Which Symbol?"))
        return LEVTRADER
    update.message.reply_text("Please enter the target leverage (Integer between 1 and 125)")
    return REALSETLEV2

def setLeverageReal(update: Update, context: CallbackContext):
    user = current_users[update.message.chat_id]
    try:
        lev = int(update.message.text)
        assert lev>=1 and lev<=125
    except:
        update.message.reply_text("This is not a valid leverage, please enter again.")
        return REALSETLEV2
    symbol = context.user_data['symbol']
    user.change_leverage(symbol,lev)
    return ConversationHandler.END
  
def set_all_proportion(update: Update, context: CallbackContext):
    if not update.message.chat_id in current_users:
        update.message.reply_text("Please initalize with /start first.")
        return ConversationHandler.END
    user = current_users[update.message.chat_id]
    logger.info(f"User {user.uname} adjusting proportion.")
    update.message.reply_text("Please enter the target proportion.")
    return ALLPROP

def setAllProportionReal(update: Update, context: CallbackContext):
    user = current_users[update.message.chat_id]
    try:
        prop = float(update.message.text)
        assert prop >=0
    except:
        update.message.reply_text("This is not a valid proportion, please enter again.")
        return ALLPROP
    user.change_all_proportion(prop)
    return ConversationHandler.END

def set_proportion(update: Update, context: CallbackContext):
    if not update.message.chat_id in current_users:
        update.message.reply_text("Please initalize with /start first.")
        return ConversationHandler.END
    user = current_users[update.message.chat_id]
    logger.info(f"User {user.uname} adjusting proportion.")
    listsymbols = user.get_symbols()
    listsymbols = [[x] for x in listsymbols]
    update.message.reply_text("Please choose the symbol to set.",reply_markup=ReplyKeyboardMarkup(listsymbols,one_time_keyboard=True,input_field_placeholder="Which Symbol?"))
    return PROPSYM

def proportion_choosesymbol(update: Update, context: CallbackContext):
    user = current_users[update.message.chat_id]
    context.user_data['symbol'] = update.message.text
    listsymbols = user.get_symbols()
    if update.message.text not in listsymbols:
        listsymbols = [[x] for x in listsymbols]
        update.message.reply_text("Sorry, the symbol is not valid, please choose again.",reply_markup=ReplyKeyboardMarkup(listsymbols,one_time_keyboard=True,input_field_placeholder="Which Symbol?"))
        return PROPSYM
    update.message.reply_text("Please enter the target proportion.")
    return REALSETPROP2

def setProportionReal(update: Update, context: CallbackContext):
    user = current_users[update.message.chat_id]
    try:
        prop = float(update.message.text)
        assert prop >=0
    except:
        update.message.reply_text("This is not a valid proportion, please enter again.")
        return REALSETPROP2
    symbol = context.user_data['symbol']
    user.change_proportion(symbol,prop)
    return ConversationHandler.END

def get_leverage(update: Update, context: CallbackContext):
    if not update.message.chat_id in current_users:
        update.message.reply_text("Please initalize with /start first.")
        return ConversationHandler.END
    user = current_users[update.message.chat_id]
    logger.info(f"User {user.uname} querying leverage.")
    listsymbols = user.get_symbols()
    listsymbols = [[x] for x in listsymbols]
    update.message.reply_text("Please choose the symbol.",reply_markup=ReplyKeyboardMarkup(listsymbols,one_time_keyboard=True,input_field_placeholder="Which Symbol?"))
    return REALSETLEV3

def getLeverageReal(update: Update, context: CallbackContext):
    user = current_users[update.message.chat_id]
    symbol = update.message.text
    listsymbols = user.get_symbols()
    if symbol not in listsymbols:
        listsymbols = [[x] for x in listsymbols]
        update.message.reply_text("Sorry, the symbol is not valid, please choose again.",reply_markup=ReplyKeyboardMarkup(listsymbols,one_time_keyboard=True,input_field_placeholder="Which Symbol?"))
        return REALSETLEV3
    result = user.get_leverage(symbol)
    update.message.reply_text(f"The leverage set for {user.name}, {symbol} is {result}x.")
    return ConversationHandler.END
  
def get_proportion(update: Update, context: CallbackContext):
    if not update.message.chat_id in current_users:
        update.message.reply_text("Please initalize with /start first.")
        return ConversationHandler.END
    user = current_users[update.message.chat_id]
    logger.info(f"User {user.uname} querying proportion.")
    listsymbols = user.get_symbols()
    listsymbols = [[x] for x in listsymbols]
    update.message.reply_text("Please choose the symbol.",reply_markup=ReplyKeyboardMarkup(listsymbols,one_time_keyboard=True,input_field_placeholder="Which Symbol?"))
    return REALSETLEV4

def getproportionReal(update: Update, context: CallbackContext):
    user = current_users[update.message.chat_id]
    symbol = update.message.text
    listsymbols = user.get_symbols()
    if symbol not in listsymbols:
        listsymbols = [[x] for x in listsymbols]
        update.message.reply_text("Sorry, the symbol is not valid, please choose again.",reply_markup=ReplyKeyboardMarkup(listsymbols,one_time_keyboard=True,input_field_placeholder="Which Symbol?"))
        return REALSETLEV4
    result = user.get_proportion(symbol)
    update.message.reply_text(f"The proportion set for {user.name}, {symbol} is {result}x.")
    return ConversationHandler.END

def end_all(update:Update, context: CallbackContext):
    if not update.message.chat_id in current_users:
        update.message.reply_text("Please initalize with /start first.")
        return
    logger.info("%s ended the service.",update.message.from_user.first_name)
    update.message.reply_text("Confirm ending the service? This means that we will not make trades for you anymore and you have to take care of the positions previously opened by yourself. Type 'yes' to confirm, /cancel to cancel.")
    return COCO

def realEndAll(update:Update, context: CallbackContext):
    del current_users[update.message.chat_id]
    update.message.reply_text("Sorry to see you go. You can press /start to restart the service.")
    return ConversationHandler.END

def set_omode(update: Update, context: CallbackContext):
    if not update.message.chat_id in current_users:
        update.message.reply_text("Please initalize with /start first.")
        return ConversationHandler.END
    user = current_users[update.message.chat_id]
    logger.info(f"User {user.uname} adjusting tmode.")
    listsymbols = user.get_symbols()
    listsymbols = [[x] for x in listsymbols]
    update.message.reply_text("Please choose the symbol to set.",reply_markup=ReplyKeyboardMarkup(listsymbols,one_time_keyboard=True,input_field_placeholder="Which Symbol?"))
    return PROPSYM2

def omode_choosesymbol(update: Update, context: CallbackContext):
    user = current_users[update.message.chat_id]
    context.user_data['symbol'] = update.message.text
    listsymbols = user.bclient.get_symbols()
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
    user = current_users[update.message.chat_id]
    try:
        tmode = int(update.message.text)
        assert tmode >=0 and tmode <=2
    except:
        update.message.reply_text("This is not a valid trading mode, please enter again.")
        return REALSETPROP3
    symbol = context.user_data['symbol']
    user.change_tmode(symbol,tmode)
    return ConversationHandler.END

def set_lmode(update: Update, context: CallbackContext):
    if not update.message.chat_id in current_users:
        update.message.reply_text("Please initalize with /start first.")
        return ConversationHandler.END
    user = current_users[update.message.chat_id]
    logger.info(f"User {user.uname} setting leverage mode.")
    update.message.reply_text("Please choose the leverage mode.")
    update.message.reply_text("0. FOLLOW: You will follow the same leverage as the trader. However, note that the leverage is only an estimate. In case the leverage information cannot be obtained, we would look at the trader's history leverage on the given symbol to determine the leverage. If that was not available as well, a default of 20x leverage would be used.") 
    update.message.reply_text("1. FIXED: You can fix your own leverage settings within this bot for every (trader,symbol) combination. Once we place an order, the leverage set by you will be used regardless of the trader's leverage. Default is 20x and can be changed later.")
    update.message.reply_text("2: IGNORE: You will follow the leverage settings on the binance site, we will not attempt to change any leverage settings for you.")
    update.message.reply_text("Please type 0,1 or 2 to indicate your choice.")
    return REALSETLEV5

def setlmodeReal(update: Update, context: CallbackContext):
    user = current_users[update.message.chat_id]
    try:
        lmode = int(update.message.text)
        assert lmode >=0 and lmode <=2
    except:
        update.message.reply_text("This is not a valid trading mode, please enter again.")
        return REALSETLEV5
    user.change_lmode(lmode)
    update.message.reply_text(f"Successfully changed leverage mode!")
    return ConversationHandler.END

def set_allomode(update: Update, context: CallbackContext):
    if not update.message.chat_id in current_users:
        update.message.reply_text("Please initalize with /start first.")
        return ConversationHandler.END
    user = current_users[update.message.chat_id]
    logger.info(f"User {user.uname} setting trading mode.")
    update.message.reply_text("Please enter the target trading mode.")
    update.message.reply_text("0. MARKET: Once we detected a change in position, you will make an order immediately at the market price. As a result, your entry price might deviate from the trader's entry price (especially when there are significant market movements).") 
    update.message.reply_text("1. LIMIT: You will make an limit order at the same price as the trader's estimated entry price. However, due to fluctuating market movements, your order might not be fulfilled.")
    update.message.reply_text("2. LIMIT, THEN MARKET: When opening positions, you will make an limit order at the same price as the trader's estimated entry price. When closing positions, you will follow market.")
    update.message.reply_text("Please type 0,1 or 2 to indicate your choice.")
    return REALSETLEV6

def setallomodeReal(update: Update, context: CallbackContext):
    user = current_users[update.message.chat_id]
    try:
        tmode = int(update.message.text)
        assert tmode >=0 and tmode <=2
    except:
        update.message.reply_text("This is not a valid trading mode, please enter again.")
        return REALSETLEV6
    user.change_all_tmode(tmode)
    update.message.reply_text(f"Successfully changed trading mode!")
    return ConversationHandler.END
    
def change_safetyratio(update: Update, context: CallbackContext):
    if not update.message.chat_id in current_users:
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
    current_users[update.message.chat_id].change_safety_ratio(safety_ratio)
    return ConversationHandler.END

def set_all_tpsl(update: Update, context: CallbackContext):
    if not update.message.chat_id in current_users:
        update.message.reply_text("Please initalize with /start first.")
        return ConversationHandler.END
    user = current_users[update.message.chat_id]
    logger.info(f"User {user.uname} adjusting TPSL.")
    update.message.reply_text("Please enter the the target Take profit/stop loss percentage, separated by space.\n(e.g. 200 300 => take profit=200%, stop loss=300%)")
    return REALSETPROP4

def setAllTpslReal(update: Update, context: CallbackContext):
    user = current_users[update.message.chat_id]
    try:
        ps = update.message.text.split(' ')
        assert len(ps) == 2
        tp = int(ps[0])
        sl = int(ps[1])
        assert tp>=-1 and tp<=400 and sl>=-1 and sl<=400
    except:
        update.message.reply_text("The percentage is invalid, please enter again.")
        return REALSETPROP4
    user.change_all_tpsl(tp,sl)
    update.message.reply_text("Take profit/stop loss ratio adjusted successfully!!!")
    return ConversationHandler.END

def set_tpsl(update: Update, context: CallbackContext):
    if not update.message.chat_id in current_users:
        update.message.reply_text("Please initalize with /start first.")
        return ConversationHandler.END
    user = current_users[update.message.chat_id]
    logger.info(f"User {user.uname} adjusting TPSL.")
    listsymbols = user.get_symbols()
    listsymbols = [[x] for x in listsymbols]
    update.message.reply_text("Please choose the symbol to set.",reply_markup=ReplyKeyboardMarkup(listsymbols,one_time_keyboard=True,input_field_placeholder="Which Symbol?"))
    return PROPSYM3

def tpsl_choosesymbol(update: Update, context: CallbackContext):
    user = current_users[update.message.chat_id]
    context.user_data['symbol'] = update.message.text
    listsymbols = user.get_symbols()
    if update.message.text not in listsymbols:
        listsymbols = [[x] for x in listsymbols]
        update.message.reply_text("Sorry, the symbol is not valid, please choose again.",reply_markup=ReplyKeyboardMarkup(listsymbols,one_time_keyboard=True,input_field_placeholder="Which Symbol?"))
        return PROPSYM3
    update.message.reply_text("Please enter the the target Take profit/stop loss percentage, separated by space.\n(e.g. 200 300 => take profit=200%, stop loss=300%)")
    return REALSETPROP5

def setTpslReal(update: Update, context: CallbackContext):
    user = current_users[update.message.chat_id]
    try:
        ps = update.message.text.split(' ')
        assert len(ps) == 2
        tp = int(ps[0])
        sl = int(ps[1])
        assert tp>=-1 and tp<=400 and sl>=-1 and sl<=400
    except:
        update.message.reply_text("The percentage is invalid, please enter again.")
        return REALSETPROP5
    symbol = context.user_data['symbol']
    user.change_tpsl(symbol,tp,sl)
    update.message.reply_text("Percentages changed successfully.")
    return ConversationHandler.END

def get_tpsl(update: Update, context: CallbackContext):
    if not update.message.chat_id in current_users:
        update.message.reply_text("Please initalize with /start first.")
        return ConversationHandler.END
    user = current_users[update.message.chat_id]
    logger.info(f"User {user.uname} querying tpsl.")
    listsymbols = user.get_symbols()
    listsymbols = [[x] for x in listsymbols]
    update.message.reply_text("Please choose the symbol.",reply_markup=ReplyKeyboardMarkup(listsymbols,one_time_keyboard=True,input_field_placeholder="Which Symbol?"))
    return REALSETLEV7

def getTpslReal(update: Update, context: CallbackContext):
    user = current_users[update.message.chat_id]
    symbol = update.message.text
    listsymbols = user.get_symbols()
    if symbol not in listsymbols:
        listsymbols = [[x] for x in listsymbols]
        update.message.reply_text("Sorry, the symbol is not valid, please choose again.",reply_markup=ReplyKeyboardMarkup(listsymbols,one_time_keyboard=True,input_field_placeholder="Which Symbol?"))
        return REALSETLEV7
    tp,sl = user.get_tpsl(symbol)
    update.message.reply_text(f"The take profit/stop loss percentage set for {user.name}, {symbol} is {tp}% and {sl}% respectively. (-1 means not set)")
    return ConversationHandler.END

class userClient:
    def __init__(self,chat_id,uname,safety_ratio,api_key,api_secret,tp=None,sl=None,tmode=None,lmode=None,positions=None,proportion=None,Leverage=None):
        self.chat_id = chat_id
        self.uname = uname
        self.name = "CalvinTsai"
        self.api_key = api_key
        self.api_secret = api_secret
        self.client = Client(api_key,api_secret)
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
        self.positions= positions
        self.tmodes = {}
        self.needprop = False
        self.needlev = False
        self.needtmode = False
        if self.positions is None:
            self.positions = {}
        if isinstance(tmode,int):
            self.needtmode = True
        else:
            self.tmodes = tmode
        self.needtp = False
        self.needsl = False
        self.take_profit_percent = {}
        if isinstance(tp,int):
            self.needtp = True
        else:
            self.take_profit_percent = tp
        self.stop_loss_percent = {}
        if isinstance(sl,int):
            self.needsl = True
        else:
            self.stop_loss_percent = sl
        self.proportion = proportion
        self.leverage = Leverage
        if self.proportion is None:
            self.proportion = {}
            self.needprop = True
        if self.leverage is None:
            self.leverage = {}
            self.needlev = True
        self.lmode = lmode
        listSymbols = self.get_symbols()
        for symbol in listSymbols:
            if self.needprop:
                self.proportion[symbol] = 0
            if self.needlev:
                self.leverage[symbol] = 20
            if self.needtmode:
                self.tmodes[symbol] = tmode
            if self.needtp:
                self.take_profit_percent[symbol] = tp
            if self.needsl:
                self.stop_loss_percent[symbol] = sl
    
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
                    self.client.futures_create_order(symbol=symbol,side=side,positionSide=positionSide,type="TAKE_PROFIT_MARKET",stopPrice=tpPrice1,workingType="MARK_PRICE",quantity=qty1)
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
                        if positionKey in self.positions:
                            self.positions[positionKey] += float(result['executedQty'])
                        else:
                            self.positions[positionKey] = float(result['executedQty'])
                        try:
                            self.tpsl_trade(symbol,result['side'],result['positionSide'],float(result['executedQty']),float(result['avgPrice']),Leverage,takeProfit,stopLoss)
                        except:
                            return
                    else:
                        if positionKey in self.positions:
                            self.positions[positionKey] -= float(result['executedQty'])
                        else:
                            self.positions[positionKey] = 0
                    return
                elif result['status'] in ["CANCELED","PENDING_CANCEL","REJECTED","EXPIRED"]:
                    updater.bot.sendMessage(chat_id=self.chat_id,text=f"Order ID {orderId} ({positionKey}) is cancelled/rejected.")
                    return
                elif result['status'] == "PARTIALLY_FILLED":
                    updatedQty = float(result['executedQty']) - executed_qty
                    if isOpen:
                        if positionKey in self.positions:
                            self.positions[positionKey] += updatedQty
                        else:
                            self.positions[positionKey] = updatedQty
                    else:
                        if positionKey in self.positions:
                            self.positions[positionKey] -= float(result['executedQty'])
                        else:
                            self.positions[positionKey] = 0
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

    def open_trade(self,tradeinfo):
        self.reload()   
        isOpen = False
        if (tradeinfo["S"] == "BUY" and tradeinfo["ps"] == "LONG") or (tradeinfo["S"]=="SELL" and tradeinfo["ps"]):
            isOpen = True
        if self.lmode != 2:
            try:
                self.client.futures_change_leverage(symbol=tradeinfo["s"],leverage=self.leverage[tradeinfo["s"]])
            except:
                pass

        quant = abs(float(tradeinfo["l"])) * self.proportion[tradeinfo["s"]]
        checkKey = tradeinfo["s"].upper()+tradeinfo["ps"]
        if not isOpen and ((checkKey not in self.positions) or (self.positions[checkKey] < quant)):
            if checkKey not in self.positions or self.positions[checkKey] == 0:
                updater.bot.sendMessage(chat_id=self.chat_id,text=f"Close {checkKey}: This trade will not be executed because your opened positions with this trader is 0.")
                return
            elif self.positions[checkKey] < quant:
                quant = min(self.positions[checkKey],quant)
                updater.bot.sendMessage(chat_id=self.chat_id,text=f"Close {checkKey}: The trade quantity will be less than expected, because you don't have enough positions to close.")
            elif quant/self.positions[checkKey] > 0.95:
                quant = max(self.positions[checkKey],quant)
        if quant == 0:
            updater.bot.sendMessage(chat_id=self.chat_id,text=f"{tradeinfo['S']} {checkKey}: This trade will not be executed because size = 0. Adjust proportion if you want to follow.")
            return
        balance,collateral,coin = 0,0,""
        try:
            coin = "USDT"
            for asset in self.client.futures_account()["assets"]:
                if asset['asset'] == "USDT":
                    balance = asset['maxWithdrawAmount']
                    break
            if tradeinfo["s"][-4:] == "BUSD":
                tradeinfo["s"] = tradeinfo["s"][:-4] + "USDT"
                updater.bot.sendMessage(chat_id=self.chat_id,text="Our system only supports USDT. This trade will be executed in USDT instead of BUSD.")
        except BinanceAPIException as e:
            coin = "USDT"
            balance = "0"
            logger.error(e) 
        balance = float(balance)
        latest_price = float(self.client.futures_mark_price(symbol=tradeinfo["s"])['markPrice'])
        collateral = (latest_price * quant) / self.leverage[tradeinfo[1]]
        if isOpen:
            updater.bot.sendMessage(chat_id=self.chat_id,text=f"For the following trade, you will need {collateral:.3f}{coin} as collateral.")
            if collateral >= balance*self.safety_ratio:
                updater.bot.sendMessage(chat_id=self.chat_id,text=f"WARNING: this trade will take up more than {self.safety_ratio} of your available balance. It will NOT be executed. Manage your risks accordingly and reduce proportion if necessary.")
                return
        reqticksize = self.ticksize[tradeinfo[1]]
        reqstepsize = self.stepsize[tradeinfo[1]]
        quant =  "{:0.0{}f}".format(quant,reqstepsize)
        target_price = "{:0.0{}f}".format(float(tradeinfo["ap"]),reqticksize)
        if self.tmodes[tradeinfo["s"]] == 0 or (self.tmodes[tradeinfo["s"]]==2 and not isOpen):
            try:
                tosend = f"Trying to execute the following trade:\nSymbol: {tradeinfo['s']}\nSide: {tradeinfo['S']}\npositionSide: {tradeinfo['ps']}\ntype: MARKET\nquantity: {quant}"
                updater.bot.sendMessage(chat_id=self.chat_id,text=tosend)
                rvalue = self.client.futures_create_order(symbol=tradeinfo['s'],side=tradeinfo['S'],positionSide=tradeinfo['ps'],type="MARKET",quantity=quant)
                logger.info(f"{self.uname} opened order.")
                positionKey = tradeinfo['s'] + tradeinfo['ps']
                t1 = threading.Thread(target=self.query_trade,args=(rvalue['orderId'],tradeinfo['s'],positionKey,isOpen,self.uname,self.take_profit_percent[tradeinfo['s']],self.stop_loss_percent[tradeinfo['s']],self.leverage[tradeinfo['s']]))
                t1.start()
            except BinanceAPIException as e:
                logger.error(e)
                if not isOpen and str(e).find("2022") >= 0:
                    positionKey = tradeinfo[1] + tradeinfo['ps']
                    self.positions[positionKey] = 0
                updater.bot.sendMessage(chat_id=self.chat_id,text=str(e))
        else:
            try:
                target_price = float(target_price)
                if tradeinfo['ps'] == "LONG":
                    target_price = min(latest_price,target_price) 
                else:
                    target_price = max(latest_price,target_price)
            except:
                pass
            target_price = "{:0.0{}f}".format(float(target_price),reqticksize)
            try:
                tosend = f"Trying to execute the following trade:\nSymbol: {tradeinfo['s']}\nSide: {tradeinfo['S']}\npositionSide: {tradeinfo['ps']}\ntype: LIMIT\nquantity: {quant}\nPrice: {target_price}"
                updater.bot.sendMessage(chat_id=self.chat_id,text=tosend)
                rvalue = self.client.futures_create_order(symbol=tradeinfo[1],side=tradeinfo['S'],positionSide=tradeinfo['ps'],type="LIMIT",quantity=quant,price=target_price,timeInForce="GTC")
                logger.info(f"{self.uname} opened order.")
                positionKey = tradeinfo[1] + tradeinfo['ps']
                t1 = threading.Thread(target=self.query_trade,args=(rvalue['orderId'],tradeinfo[1],positionKey,isOpen,self.uname,self.take_profit_percent[tradeinfo['s']],self.stop_loss_percent[tradeinfo['s']],self.leverage[tradeinfo['s']]))
                t1.start()
            except BinanceAPIException as e:
                logger.error(e)
                updater.bot.sendMessage(chat_id=self.chat_id,text=str(e))

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


def main():
    dispatcher = updater.dispatcher
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            AUTH: [MessageHandler(Filters.text & ~Filters.command, auth_check)],
            DISCLAIMER:[MessageHandler(Filters.regex('^(yes)$'),disclaimer_check)],
            APIKEY:[MessageHandler(Filters.text & ~Filters.command, check_api)],
            APISECRET: [MessageHandler(Filters.text & ~Filters.command, check_secret)],
            SAFERATIO: [MessageHandler(Filters.text & ~Filters.command, check_ratio)],
            TMODE: [MessageHandler(Filters.regex('^(0|1|2)$'),tmode_confirm)],    
            LMODE: [MessageHandler(Filters.regex('^(0|1|2)$'),lmode_confirm)],
            TP: [MessageHandler(Filters.text & ~Filters.command, tp_confirm)],
            SL: [MessageHandler(Filters.text & ~Filters.command, sl_confirm)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    conv_handler2 = ConversationHandler(
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
    conv_handler6 = ConversationHandler(
        entry_points=[CommandHandler('setallleverage',setAllLeverage)],
        states={
            REALSETLEV:[MessageHandler(Filters.text & ~Filters.command,setAllLeverageReal)]
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    conv_handler7 = ConversationHandler(
        entry_points=[CommandHandler('setleverage',set_leverage)],
        states={
            LEVTRADER:[MessageHandler(Filters.text & ~Filters.command,leverage_choosesymbol)],
            REALSETLEV2:[MessageHandler(Filters.text & ~Filters.command,setLeverageReal)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    conv_handler8 = ConversationHandler(
        entry_points=[CommandHandler('setallproportion',set_all_proportion)],
        states={
            ALLPROP:[MessageHandler(Filters.text & ~Filters.command,setAllProportionReal)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    conv_handler9 = ConversationHandler(
        entry_points=[CommandHandler('setproportion',set_proportion)],
        states={
            PROPSYM:[MessageHandler(Filters.text & ~Filters.command,proportion_choosesymbol)],
            REALSETPROP2:[MessageHandler(Filters.text & ~Filters.command,setProportionReal)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    conv_handler10 = ConversationHandler(
        entry_points=[CommandHandler('getleverage',get_leverage)],
        states={
            REALSETLEV3:[MessageHandler(Filters.text & ~Filters.command,getLeverageReal)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    conv_handler11 = ConversationHandler(
        entry_points=[CommandHandler('getproportion',get_proportion)],
        states={
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
            PROPSYM2:[MessageHandler(Filters.text & ~Filters.command,omode_choosesymbol)],
            REALSETPROP3:[MessageHandler(Filters.regex('^(0|1|2)$'),setomodeReal)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    conv_handler14 = ConversationHandler(
        entry_points=[CommandHandler('setlmode',set_lmode)],
        states={
            REALSETLEV5:[MessageHandler(Filters.regex('^(0|1|2)$'),setlmodeReal)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    conv_handler15 = ConversationHandler(
        entry_points=[CommandHandler('setalltmode',set_allomode)],
        states={
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
            REALSETPROP4:[MessageHandler(Filters.text & ~Filters.command,setAllTpslReal)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    conv_handler18 = ConversationHandler(
        entry_points=[CommandHandler('settpsl',set_tpsl)],
        states={
            PROPSYM3:[MessageHandler(Filters.text & ~Filters.command,tpsl_choosesymbol)],
            REALSETPROP5:[MessageHandler(Filters.text & ~Filters.command,setTpslReal)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    conv_handler19 = ConversationHandler(
        entry_points=[CommandHandler('gettpsl',get_tpsl)],
        states={
            REALSETLEV7:[MessageHandler(Filters.text & ~Filters.command,getTpslReal)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )   
    global current_stream 
    dispatcher.add_handler(conv_handler)
    dispatcher.add_handler(conv_handler2)
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
    dispatcher.add_handler(CommandHandler("view", view_position))
    current_stream = getStreamData()
    current_stream.start()
    thr = threading.Thread(target=automatic_reload)
    thr.start()
    thr2 = threading.Thread(target=get_newest_trade)
    thr2.start()
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()