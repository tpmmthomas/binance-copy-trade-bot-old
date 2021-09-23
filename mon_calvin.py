import os
from telegram import chat
import constants as cnt
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException
from time import sleep
import binance
import pandas as pd
from datetime import datetime, timedelta
import threading
import time
import logging
import math
import queue
import pickle
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
import bybit
import random
import matplotlib.pyplot as plt
import hmac, hashlib, time, requests
from multiprocessing import Process

q = queue.Queue(200)
is_reloading = False
reloading = False
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
(
    AUTH,
    SEP1,
    SEP2,
    PLATFORM,
    CHECKPROP,
    COCO,
    TRADERURL,
    MUTE1,
    MUTE2,
    ALLPROP2,
    REALSETPROP4,
    LEVTRADER6,
    LEVTRADER7,
    REALSETLEV7,
    LEVTRADER3,
    REALSETLEV4,
    LEVTRADER4,
    REALSETLEV5,
    LEVTRADER5,
    REALSETLEV6,
    TRADERURL2,
    LEVTRADER2,
    REALSETLEV3,
    TRADERNAME,
    AUTH2,
    ANNOUNCE,
    DISCLAIMER,
    VIEWTRADER,
    TP,
    SL,
    TOTRADE,
    TMODE,
    LMODE,
    APIKEY,
    APISECRET,
    ALLLEV,
    REALSETLEV,
    LEVTRADER,
    LEVSYM,
    REALSETLEV2,
    ALLPROP,
    REALSETPROP,
    PROPTRADER,
    PROPSYM,
    REALSETPROP2,
    PROPTRADER3,
    PROPSYM3,
    REALSETPROP5,
    PROPTRADER2,
    PROPSYM2,
    REALSETPROP3,
    SAFERATIO,
    SEP3,
    CP1,
    UPDATEPROP,
) = range(55)

logger = logging.getLogger(__name__)
updater = Updater(cnt.bot_token2)

current_users = {}
current_stream = None
dictLock = threading.Lock()
stop_update = False


def round_up(n, decimals=0):
    multiplier = 10 ** decimals
    return math.ceil(n * multiplier) / multiplier


def show_positions():
    get_positions()
    time.sleep(2)
    global stop_update
    stop_update = False
    get_positions()
    for chat_id in current_users:
        pos = lastPositions
        updater.bot.sendMessage(chat_id=chat_id, text="The latest position:\n" + pos)


class getStreamData(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.client = Client(cnt.api_key, cnt.api_secret)
        self.lastPositions = None
        self.pauseload = threading.Event()

    def get_balance(self):
        result = self.client.futures_account()["assets"]
        for asset in result:
            if asset["asset"] == "USDT":
                return float(asset["marginBalance"])

    def run(self):
        while True:
            time.sleep(4)
            if self.pauseload.is_set():
                continue
            try:
                result = self.client.futures_position_information()
            except BinanceAPIException as e:
                logger.error("Cannot retrieve latest position.")
                logger.error(str(e))
                continue
            except:
                logger.error("Other errors")
                continue
            symbol = []
            size = []
            EnPrice = []
            MarkPrice = []
            PNL = []
            margin = []
            listTradingSymbols = []
            for pos in result:
                if float(pos["positionAmt"]) != 0:
                    symbol.append(pos["symbol"])
                    tsize = pos["positionAmt"]
                    size.append(tsize)
                    EnPrice.append(pos["entryPrice"])
                    MarkPrice.append(pos["markPrice"])
                    PNL.append(pos["unRealizedProfit"])
                    margin.append(pos["leverage"])
                    listTradingSymbols.append(pos["symbol"])
                    for user in current_users:
                        if current_users[user].lmode == 0:
                            current_users[user].leverage[pos["symbol"]] = int(
                                pos["leverage"]
                            )
            newPosition = pd.DataFrame(
                {
                    "symbol": symbol,
                    "size": size,
                    "Entry Price": EnPrice,
                    "Mark Price": MarkPrice,
                    "PNL": PNL,
                    "leverage": margin,
                }
            )
            isDiff, diff, isCloseAll = self.compare(self.lastPositions, newPosition)
            if isDiff and not diff.empty:
                # logger.info("Yes")
                process_newest_position(diff, newPosition, isCloseAll)
            self.lastPositions = newPosition

    def pause(self):
        self.pauseload.set()

    def resume(self):
        self.pauseload.clear()

    def compare(self, df, df2):
        if df is None or df2 is None:
            return False, None, None
        toComp = df[["symbol", "size"]]
        toComp2 = df2[["symbol", "size"]]
        if toComp.equals(toComp2):
            return False, None, None  #
        txtype = []
        txsymbol = []
        txsize = []
        executePrice = []
        isCloseAll = []
        if df.empty:
            for index, row in df2.iterrows():
                size = row["size"]
                if isinstance(size, str):
                    size = size.replace(",", "")
                size = float(size)
                if size > 0:
                    txtype.append("OpenLong")
                    txsymbol.append(row["symbol"])
                    txsize.append(size)
                    executePrice.append(row["Entry Price"])
                    isCloseAll.append(False)
                else:
                    txtype.append("OpenShort")
                    txsymbol.append(row["symbol"])
                    txsize.append(size)
                    executePrice.append(row["Entry Price"])
                    isCloseAll.append(False)
            txs = pd.DataFrame(
                {
                    "txtype": txtype,
                    "symbol": txsymbol,
                    "size": txsize,
                    "ExecPrice": executePrice,
                }
            )
        elif df2.empty:
            for index, row in df.iterrows():
                size = row["size"]
                if isinstance(size, str):
                    size = size.replace(",", "")
                size = float(size)
                if size > 0:
                    txtype.append("CloseLong")
                    txsymbol.append(row["symbol"])
                    txsize.append(-size)
                    executePrice.append(row["Mark Price"])
                    isCloseAll.append(True)
                else:
                    txtype.append("CloseShort")
                    txsymbol.append(row["symbol"])
                    txsize.append(-size)
                    executePrice.append(row["Mark Price"])
                    isCloseAll.append(True)
            txs = pd.DataFrame(
                {
                    "txtype": txtype,
                    "symbol": txsymbol,
                    "size": txsize,
                    "ExecPrice": executePrice,
                }
            )
        else:
            df, df2 = df.copy(), df2.copy()
            for index, row in df.iterrows():
                hasChanged = False
                temp = df2["symbol"] == row["symbol"]
                idx = df2.index[temp]
                size = row["size"]
                if isinstance(size, str):
                    size = size.replace(",", "")
                size = float(size)
                oldentry = row["Entry Price"]
                if isinstance(oldentry, str):
                    oldentry = oldentry.replace(",", "")
                oldentry = float(oldentry)
                oldmark = row["Mark Price"]
                if isinstance(oldmark, str):
                    oldmark = oldmark.replace(",", "")
                oldmark = float(oldmark)
                isPositive = size >= 0
                for r in idx:
                    df2row = df2.loc[r].values
                    newsize = df2row[1]
                    if isinstance(newsize, str):
                        newsize = newsize.replace(",", "")
                    newsize = float(newsize)
                    newentry = df2row[2]
                    if isinstance(newentry, str):
                        newentry = newentry.replace(",", "")
                    newentry = float(newentry)
                    newmark = df2row[3]
                    if isinstance(newmark, str):
                        newmark = newmark.replace(",", "")
                    newmark = float(newmark)
                    if newsize == size:
                        df2 = df2.drop(r)
                        hasChanged = True
                        break
                    if isPositive and newsize > 0:
                        changesize = newsize - size
                        if changesize > 0:
                            txtype.append("OpenLong")
                            txsymbol.append(df2row[0])
                            txsize.append(changesize)
                            isCloseAll.append(False)
                            try:
                                exp = (
                                    newentry * newsize - oldentry * size
                                ) / changesize
                            except:
                                exp = 0
                            executePrice.append(exp)
                        else:
                            txtype.append("CloseLong")
                            txsymbol.append(df2row[0])
                            txsize.append(changesize)
                            executePrice.append(newmark)
                            isCloseAll.append(False)
                        df2 = df2.drop(r)
                        hasChanged = True
                        break
                    if not isPositive and newsize < 0:
                        changesize = newsize - size
                        if changesize > 0:
                            txtype.append("CloseShort")
                            txsymbol.append(df2row[0])
                            txsize.append(changesize)
                            executePrice.append(newmark)
                            isCloseAll.append(False)
                        else:
                            txtype.append("OpenShort")
                            txsymbol.append(df2row[0])
                            txsize.append(changesize)
                            isCloseAll.append(False)
                            try:
                                exp = (
                                    newentry * newsize - oldentry * size
                                ) / changesize
                            except:
                                exp = 0
                            executePrice.append(exp)
                        df2 = df2.drop(r)
                        hasChanged = True
                        break
                if not hasChanged:
                    if size > 0:
                        txtype.append("CloseLong")
                        txsymbol.append(row["symbol"])
                        txsize.append(-size)
                        executePrice.append(oldmark)
                        isCloseAll.append(True)
                    else:
                        txtype.append("CloseShort")
                        txsymbol.append(row["symbol"])
                        txsize.append(-size)
                        executePrice.append(oldmark)
                        isCloseAll.append(True)
            for index, row in df2.iterrows():
                size = row["size"]
                if isinstance(size, str):
                    size = size.replace(",", "")
                size = float(size)
                if size > 0:
                    txtype.append("OpenLong")
                    txsymbol.append(row["symbol"])
                    txsize.append(size)
                    executePrice.append(row["Entry Price"])
                    isCloseAll.append(False)
                else:
                    txtype.append("OpenShort")
                    txsymbol.append(row["symbol"])
                    txsize.append(size)
                    executePrice.append(row["Entry Price"])
                    isCloseAll.append(False)
            txs = pd.DataFrame(
                {
                    "txType": txtype,
                    "symbol": txsymbol,
                    "size": txsize,
                    "ExecPrice": executePrice,
                }
            )
        return True, txs, isCloseAll

    def stop(self):
        self.isStop.set()


def process_newest_position(diff, df, isCloseAll):
    for chat_id in current_users:
        if df.empty:
            updater.bot.sendMessage(
                chat_id=chat_id, text="The newest position:\nNo Position."
            )
        else:
            updater.bot.sendMessage(
                chat_id=chat_id, text="The newest position:\n" + df.to_string()
            )
        tosend = (
            f"*The positions changed in Kevin's account:*\n" + diff.to_string() + "\n"
        )
        updater.bot.sendMessage(chat_id=chat_id, text=tosend)
        current_users[chat_id].open_trade(diff, isCloseAll)


def automatic_reload():
    global current_stream
    while True:
        time.sleep(3 * 60 * 60)
        for user in current_users:
            current_users[user].reload()
        if not is_reloading:
            save_to_file(None, None)


def start(update: Update, context: CallbackContext) -> int:
    if update.message.chat_id in current_users:
        update.message.reply_text(
            "You have already initalized! Please use other commands, or use /end to end current session before initializing another."
        )
        return ConversationHandler.END
    update.message.reply_text(
        f"*Welcome {update.message.from_user.first_name}! Note that this bot is only for following Kevin's account.* Before you start, please type in the access code (6 digits).",
        parse_mode=telegram.ParseMode.MARKDOWN,
    )
    context.user_data["uname"] = update.message.from_user.first_name
    return AUTH


def auth_check(update: Update, context: CallbackContext) -> int:
    user = update.message.from_user
    logger.info(
        "%s is doing authentication check.", update.message.from_user.first_name
    )
    if update.message.text == cnt.auth_code:
        update.message.reply_text(
            'Great! Please read the following disclaimer:\nThis software is for non-commercial purposes only.\n\
Do not risk money which you are afraid to lose.\nUSE THIS SOFTWARE AT YOUR OWN RISK.\n*THE DEVELOPERS ASSUME NO RESPONSIBILITY FOR YOUR TRADING RESULTS.*\n\
Do not engage money before you understand how it works and what profit/loss you should expect. \n\
Type "yes" (lowercase) if you agree. Otherwise type /cancel and exit.',
            parse_mode=telegram.ParseMode.MARKDOWN,
        )
        return DISCLAIMER
    else:
        update.message.reply_text(
            "Sorry! The access code is wrong. Type /start again if you need to retry."
        )
        return ConversationHandler.END


def disclaimer_check(update: Update, context: CallbackContext):
    logger.info("%s has agreed to the disclaimer.", update.message.from_user.first_name)
    update.message.reply_text(
        "Please choose the platform:\n1. AAX\n2. Bybit\n3.Binance\nPlease enter your choice (1,2,3)"
    )
    return PLATFORM


def check_platform(update: Update, context: CallbackContext):
    platform = int(update.message.text)
    context.user_data["platform"] = platform
    if platform == 3:
        update.message.reply_text("Please provide your API Key from Binance.")
    elif platform == 2:
        update.message.reply_text("Please provide your API Key from Bybit.")
    else:
        update.message.reply_text("Please provide your API Key from AAX.")
    update.message.reply_text(
        "*SECURITY WARNING*\nTo ensure safety of funds, please note the following before providing your API key:\n1. Set up a new key for this program, don't reuse your other API keys.\n2. Restrict access to this IP: *35.229.163.161*\n3. Only allow these API Restrictions: 'Enable Reading' and 'Enable Futures'.",
        parse_mode=telegram.ParseMode.MARKDOWN,
    )
    return APIKEY


def check_api(update: Update, context: CallbackContext):
    context.user_data["api_key"] = update.message.text
    if not update.message.text.isalnum():
        update.message.reply_text("Your API key is invalid, please enter again.")
        return APIKEY
    update.message.reply_text(
        "Please provide your Secret Key.\n*DELETE YOUR MESSAGE IMMEDIATELY AFTERWARDS.*",
        parse_mode=telegram.ParseMode.MARKDOWN,
    )
    return APISECRET


def check_secret(update: Update, context: CallbackContext):
    context.user_data["api_secret"] = update.message.text
    if not update.message.text.isalnum():
        update.message.reply_text("Your secret key is invalid, please enter again.")
        return APISECRET
    update.message.reply_text(
        "Please enter the amount (in USDT) you plan to invest with this bot. We will calculate the suggested proportion for you."
    )
    return CHECKPROP


def check_ratio(update: Update, context: CallbackContext):
    try:
        ratio = float(update.message.text)
        assert ratio >= 100
        ratio = ratio / current_stream.get_balance()
        ratio = round(ratio, 6)
    except:
        update.message.reply_text(
            "Sorry, you amount is wrong or too small (minimum 100 USDT). Please reenter."
        )
        return CHECKPROP
    update.message.reply_text(f"Your calculated proportion is {ratio}x.")
    update.message.reply_text(
        "By default, you will follow exactly every order made in Kevin's account, except the quantity will be multiplied by the proportion. You may adjust the settings including leverage, proportion, take_profit, stop_loss etc, but do that with EXTREME CAUTION. Use the Menu to see the available settings."
    )
    current_users[update.message.chat_id] = userClient(
        update.message.chat_id,
        context.user_data["uname"],
        1,
        context.user_data["api_key"],
        context.user_data["api_secret"],
        ratio,
        tplatform=context.user_data["platform"],
    )
    update.message.reply_text("You have successfully initialized! :)")
    return ConversationHandler.END


def help_command(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /help is issued."""
    update.message.reply_text(
        "***GENERAL***\n/start: Initalize and begin following traders\n/admin: Announce message to all users (need authorization code)\n/help: view list of commands\n/view : view the current positions.\n/end: End the service.\n***TRADE COPY CONFIG***\n/setproportion: Set the trade copy proportion for a (trader,symbol) pair.\n/setallproportion: Set the trade copy proportion for a trader, all symbols.\n/getproportion: Get the current proportion for a (trader,symbol) pair\n/setleverage: set leverage for a (trader,symbol) pair.\n/setallleverage: set leverage for a trader, all symbols.\n/getleverage: Get the current leverage for the (trader,symbol) pair.\n/setlmode: Change the leverage mode of a trader.\n/settmode: Change the trading mode for a (trader,symbol) pair.\n/setalltmode: Change trading mode for a trader, all symbols.\n/changesr: Change safety ratio\n/gettpsl: Get the take profit/stop loss ratio of a (trader,symbol) pair.\n/settpsl: Set the take profit/stop loss ratio of a (trader,symbol) pair.\n/setalltpsl: Set the take profit/stop loss ratio of a trader, all symbols."
    )


def end(update: Update, context: CallbackContext):
    if not update.message.chat_id in current_users:
        update.message.reply_text(
            "You have already initialized. No need to do it again."
        )
        return
    update.message.reply_text("Bye!")
    current_users.remove(update.message.chat_id)


def cancel(update: Update, context: CallbackContext) -> int:
    """Cancels and ends the conversation."""
    user = update.message.from_user
    logger.info(
        "User %s canceled the conversation.", update.message.from_user.first_name
    )
    update.message.reply_text("Operation canceled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


def end_everyone(update: Update, context: CallbackContext):
    global current_users
    for user in current_users:
        updater.bot.sendMessage(
            chat_id=user, text="Your service has been force ended by admin."
        )
    current_users = {}
    logger.info("Everyone's service has ended.")
    return ConversationHandler.END


def admin(update: Update, context: CallbackContext):
    update.message.reply_text("Please enter admin authorization code to continue.")
    return AUTH2


def auth_check2(update: Update, context: CallbackContext) -> int:
    user = update.message.from_user
    logger.info(
        "%s is doing authentication check for admin.",
        update.message.from_user.first_name,
    )
    if update.message.text == cnt.admin_code:
        update.message.reply_text(
            "Great! Please enter the message that you want to announce to all users. /cancel to cancel, /save to save users data, /endall to end all users."
        )
        return ANNOUNCE
    else:
        update.message.reply_text(
            "Sorry! The access code is wrong. Type /admin again if you need to retry."
        )
        return ConversationHandler.END


def announce(update: Update, context: CallbackContext):
    for user in current_users:
        updater.bot.sendMessage(chat_id=user, text=update.message.text)
    logger.info("Message announced for all users.")
    return ConversationHandler.END


def save_to_file(update: Update, context: CallbackContext):
    save_items = []
    for user in current_users:
        user = current_users[user]
        save_items.append(
            {
                "chat_id": user.chat_id,
                "uname": user.uname,
                "safety_ratio": user.safety_ratio,
                "api_key": user.api_key,
                "api_secret": user.api_secret,
                "tp": user.take_profit_percent,
                "sl": user.stop_loss_percent,
                "lmode": user.lmode,
                "positions": user.positions,
                "proportion": user.proportion,
                "leverage": user.leverage,
                "platform": user.tplatform,
            }
        )
    with open("userdata_calvin.pickle", "wb") as f:
        pickle.dump(save_items, f)
    logger.info("Saved user current state.")
    return ConversationHandler.END


def view_position(update: Update, context: CallbackContext):
    if not update.message.chat_id in current_users:
        update.message.reply_text("Please initalize with /start first.")
        return
    position = current_stream.lastPositions
    bal = float(current_stream.get_balance())
    if position is None:
        updater.bot.sendMessage(chat_id=update.message.chat_id, text="Error.")
    elif position.empty:
        updater.bot.sendMessage(chat_id=update.message.chat_id, text="No Position.")
    else:
        updater.bot.sendMessage(
            chat_id=update.message.chat_id, text=position.to_string()
        )
    if not bal is None:
        roi = "{:.2f}".format((bal - 38500) / 38500 * 100)
        updater.bot.sendMessage(
            chat_id=update.message.chat_id,
            text=f"Account current USDT balance: {bal}\nROI%: {roi}%",
        )
    return


def setAllLeverage(update: Update, context: CallbackContext):
    if not update.message.chat_id in current_users:
        update.message.reply_text("Please initalize with /start first.")
        return ConversationHandler.END
    if current_users[update.message.chat_id].lmode == 0:
        update.message.reply_text(
            "You leverage currently is following the trader. Change your leverage mode first with /setlmode before you can fix your own leverage."
        )
        return ConversationHandler.END
    user = current_users[update.message.chat_id]
    logger.info(f"User {user.uname} adjusting leverage.")
    update.message.reply_text(
        "Please enter the target leverage (Integer between 1 and 125)"
    )
    return REALSETLEV


def setAllLeverageReal(update: Update, context: CallbackContext):
    user = current_users[update.message.chat_id]
    try:
        lev = int(update.message.text)
        assert lev >= 1 and lev <= 125
    except:
        update.message.reply_text("This is not a valid leverage, please enter again.")
        return REALSETLEV
    user.change_all_leverage(lev)
    return ConversationHandler.END


def set_leverage(update: Update, context: CallbackContext):
    if not update.message.chat_id in current_users:
        update.message.reply_text("Please initalize with /start first.")
        return ConversationHandler.END
    if current_users[update.message.chat_id].lmode == 0:
        update.message.reply_text(
            "You leverage currently is following the trader. Change your leverage mode first with /setlmode before you can fix your own leverage."
        )
        return ConversationHandler.END
    listsymbols = current_users[update.message.chat_id].get_symbols()
    listsymbols = [[x] for x in listsymbols]
    update.message.reply_text(
        "Please choose the symbol to set.",
        reply_markup=ReplyKeyboardMarkup(
            listsymbols, one_time_keyboard=True, input_field_placeholder="Which Symbol?"
        ),
    )
    return LEVTRADER


def leverage_choosesymbol(update: Update, context: CallbackContext):
    user = current_users[update.message.chat_id]
    context.user_data["symbol"] = update.message.text
    listsymbols = user.get_symbols()
    if update.message.text not in listsymbols:
        listsymbols = [[x] for x in listsymbols]
        update.message.reply_text(
            "Sorry, the symbol is not valid, please choose again.",
            reply_markup=ReplyKeyboardMarkup(
                listsymbols,
                one_time_keyboard=True,
                input_field_placeholder="Which Symbol?",
            ),
        )
        return LEVTRADER
    update.message.reply_text(
        "Please enter the target leverage (Integer between 1 and 125)"
    )
    return REALSETLEV2


def setLeverageReal(update: Update, context: CallbackContext):
    user = current_users[update.message.chat_id]
    try:
        lev = int(update.message.text)
        assert lev >= 1 and lev <= 125
    except:
        update.message.reply_text("This is not a valid leverage, please enter again.")
        return REALSETLEV2
    symbol = context.user_data["symbol"]
    user.change_leverage(symbol, lev)
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
        assert prop >= 0
    except:
        update.message.reply_text("This is not a valid proportion, please enter again.")
        return ALLPROP
    user.change_all_proportion(prop)
    return ConversationHandler.END


def update_proportion(update: Update, context: CallbackContext):
    if not update.message.chat_id in current_users:
        update.message.reply_text("Please initalize with /start first.")
        return ConversationHandler.END
    user = current_users[update.message.chat_id]
    logger.info(f"User {user.uname} adjusting proportion.")
    update.message.reply_text(
        "Please enter the amount you want to invest (minumum 100 USDT)."
    )
    return UPDATEPROP


def updateProportionReal(update: Update, context: CallbackContext):
    user = current_users[update.message.chat_id]
    try:
        prop = float(update.message.text)
        assert prop >= 100
    except:
        update.message.reply_text("This is not a valid amount, please enter again.")
        return UPDATEPROP
    newprop = prop / current_stream.get_balance()
    newprop = round_up(newprop, 6)
    update.message.reply_text(f"Your newest proportion is {newprop}.")
    user.change_all_proportion(newprop)
    return ConversationHandler.END


def set_proportion(update: Update, context: CallbackContext):
    if not update.message.chat_id in current_users:
        update.message.reply_text("Please initalize with /start first.")
        return ConversationHandler.END
    user = current_users[update.message.chat_id]
    logger.info(f"User {user.uname} adjusting proportion.")
    listsymbols = user.get_symbols()
    listsymbols = [[x] for x in listsymbols]
    update.message.reply_text(
        "Please choose the symbol to set.",
        reply_markup=ReplyKeyboardMarkup(
            listsymbols, one_time_keyboard=True, input_field_placeholder="Which Symbol?"
        ),
    )
    return PROPSYM


def proportion_choosesymbol(update: Update, context: CallbackContext):
    user = current_users[update.message.chat_id]
    context.user_data["symbol"] = update.message.text
    listsymbols = user.get_symbols()
    if update.message.text not in listsymbols:
        listsymbols = [[x] for x in listsymbols]
        update.message.reply_text(
            "Sorry, the symbol is not valid, please choose again.",
            reply_markup=ReplyKeyboardMarkup(
                listsymbols,
                one_time_keyboard=True,
                input_field_placeholder="Which Symbol?",
            ),
        )
        return PROPSYM
    update.message.reply_text("Please enter the target proportion.")
    return REALSETPROP2


def setProportionReal(update: Update, context: CallbackContext):
    user = current_users[update.message.chat_id]
    try:
        prop = float(update.message.text)
        assert prop >= 0
    except:
        update.message.reply_text("This is not a valid proportion, please enter again.")
        return REALSETPROP2
    symbol = context.user_data["symbol"]
    user.change_proportion(symbol, prop)
    return ConversationHandler.END


def get_leverage(update: Update, context: CallbackContext):
    if not update.message.chat_id in current_users:
        update.message.reply_text("Please initalize with /start first.")
        return ConversationHandler.END
    user = current_users[update.message.chat_id]
    logger.info(f"User {user.uname} querying leverage.")
    listsymbols = user.get_symbols()
    listsymbols = [[x] for x in listsymbols]
    update.message.reply_text(
        "Please choose the symbol.",
        reply_markup=ReplyKeyboardMarkup(
            listsymbols, one_time_keyboard=True, input_field_placeholder="Which Symbol?"
        ),
    )
    return REALSETLEV3


def getLeverageReal(update: Update, context: CallbackContext):
    user = current_users[update.message.chat_id]
    symbol = update.message.text
    listsymbols = user.get_symbols()
    if symbol not in listsymbols:
        listsymbols = [[x] for x in listsymbols]
        update.message.reply_text(
            "Sorry, the symbol is not valid, please choose again.",
            reply_markup=ReplyKeyboardMarkup(
                listsymbols,
                one_time_keyboard=True,
                input_field_placeholder="Which Symbol?",
            ),
        )
        return REALSETLEV3
    result = user.get_leverage(symbol)
    update.message.reply_text(
        f"The leverage set for {user.name}, {symbol} is {result}x."
    )
    return ConversationHandler.END


def get_proportion(update: Update, context: CallbackContext):
    if not update.message.chat_id in current_users:
        update.message.reply_text("Please initalize with /start first.")
        return ConversationHandler.END
    user = current_users[update.message.chat_id]
    logger.info(f"User {user.uname} querying proportion.")
    listsymbols = user.get_symbols()
    listsymbols = [[x] for x in listsymbols]
    update.message.reply_text(
        "Please choose the symbol.",
        reply_markup=ReplyKeyboardMarkup(
            listsymbols, one_time_keyboard=True, input_field_placeholder="Which Symbol?"
        ),
    )
    return REALSETLEV4


def getproportionReal(update: Update, context: CallbackContext):
    user = current_users[update.message.chat_id]
    symbol = update.message.text
    listsymbols = user.get_symbols()
    if symbol not in listsymbols:
        listsymbols = [[x] for x in listsymbols]
        update.message.reply_text(
            "Sorry, the symbol is not valid, please choose again.",
            reply_markup=ReplyKeyboardMarkup(
                listsymbols,
                one_time_keyboard=True,
                input_field_placeholder="Which Symbol?",
            ),
        )
        return REALSETLEV4
    result = user.get_proportion(symbol)
    update.message.reply_text(
        f"The proportion set for {user.name}, {symbol} is {result}x."
    )
    return ConversationHandler.END


def end_all(update: Update, context: CallbackContext):
    if not update.message.chat_id in current_users:
        update.message.reply_text("Please initalize with /start first.")
        return
    logger.info("%s ended the service.", update.message.from_user.first_name)
    update.message.reply_text(
        "Confirm ending the service? This means that we will not make trades for you anymore and you have to take care of the positions previously opened by yourself. Type 'yes' to confirm, /cancel to cancel."
    )
    return COCO


def realEndAll(update: Update, context: CallbackContext):
    del current_users[update.message.chat_id]
    update.message.reply_text(
        "Sorry to see you go. You can press /start to restart the service."
    )
    return ConversationHandler.END


def set_lmode(update: Update, context: CallbackContext):
    if not update.message.chat_id in current_users:
        update.message.reply_text("Please initalize with /start first.")
        return ConversationHandler.END
    user = current_users[update.message.chat_id]
    logger.info(f"User {user.uname} setting leverage mode.")
    update.message.reply_text("Please choose the leverage mode.")
    update.message.reply_text(
        "0. FOLLOW: You will follow the same leverage as the trader. However, note that the leverage is only an estimate. In case the leverage information cannot be obtained, we would look at the trader's history leverage on the given symbol to determine the leverage. If that was not available as well, a default of 2x leverage would be used."
    )
    update.message.reply_text(
        "1. FIXED: You can fix your own leverage settings within this bot for every (trader,symbol) combination. Once we place an order, the leverage set by you will be used regardless of the trader's leverage. Default is 2x and can be changed later."
    )
    update.message.reply_text("Please type 0 or 1 to indicate your choice.")
    return REALSETLEV5


def setlmodeReal(update: Update, context: CallbackContext):
    user = current_users[update.message.chat_id]
    try:
        lmode = int(update.message.text)
        assert lmode >= 0 and lmode <= 2
    except:
        update.message.reply_text(
            "This is not a valid trading mode, please enter again."
        )
        return REALSETLEV5
    user.change_lmode(lmode)
    update.message.reply_text(f"Successfully changed leverage mode!")
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
        assert safety_ratio >= 0 and safety_ratio <= 1
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
    update.message.reply_text(
        "Please enter the the target Take profit/stop loss percentage, separated by space.\n(e.g. 200 300 => take profit=200%, stop loss=300%)"
    )
    return REALSETPROP4


def setAllTpslReal(update: Update, context: CallbackContext):
    user = current_users[update.message.chat_id]
    try:
        ps = update.message.text.split(" ")
        assert len(ps) == 2
        tp = int(ps[0])
        sl = int(ps[1])
        assert tp >= -1 and tp <= 400 and sl >= -1 and sl <= 400
    except:
        update.message.reply_text("The percentage is invalid, please enter again.")
        return REALSETPROP4
    user.change_all_tpsl(tp, sl)
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
    update.message.reply_text(
        "Please choose the symbol to set.",
        reply_markup=ReplyKeyboardMarkup(
            listsymbols, one_time_keyboard=True, input_field_placeholder="Which Symbol?"
        ),
    )
    return PROPSYM3


def tpsl_choosesymbol(update: Update, context: CallbackContext):
    user = current_users[update.message.chat_id]
    context.user_data["symbol"] = update.message.text
    listsymbols = user.get_symbols()
    if update.message.text not in listsymbols:
        listsymbols = [[x] for x in listsymbols]
        update.message.reply_text(
            "Sorry, the symbol is not valid, please choose again.",
            reply_markup=ReplyKeyboardMarkup(
                listsymbols,
                one_time_keyboard=True,
                input_field_placeholder="Which Symbol?",
            ),
        )
        return PROPSYM3
    update.message.reply_text(
        "Please enter the the target Take profit/stop loss percentage, separated by space.\n(e.g. 200 300 => take profit=200%, stop loss=300%)"
    )
    return REALSETPROP5


def setTpslReal(update: Update, context: CallbackContext):
    user = current_users[update.message.chat_id]
    try:
        ps = update.message.text.split(" ")
        assert len(ps) == 2
        tp = int(ps[0])
        sl = int(ps[1])
        assert tp >= -1 and tp <= 400 and sl >= -1 and sl <= 400
    except:
        update.message.reply_text("The percentage is invalid, please enter again.")
        return REALSETPROP5
    symbol = context.user_data["symbol"]
    user.change_tpsl(symbol, tp, sl)
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
    update.message.reply_text(
        "Please choose the symbol.",
        reply_markup=ReplyKeyboardMarkup(
            listsymbols, one_time_keyboard=True, input_field_placeholder="Which Symbol?"
        ),
    )
    return REALSETLEV7


def getTpslReal(update: Update, context: CallbackContext):
    user = current_users[update.message.chat_id]
    symbol = update.message.text
    listsymbols = user.get_symbols()
    if symbol not in listsymbols:
        listsymbols = [[x] for x in listsymbols]
        update.message.reply_text(
            "Sorry, the symbol is not valid, please choose again.",
            reply_markup=ReplyKeyboardMarkup(
                listsymbols,
                one_time_keyboard=True,
                input_field_placeholder="Which Symbol?",
            ),
        )
        return REALSETLEV7
    tp, sl = user.get_tpsl(symbol)
    update.message.reply_text(
        f"The take profit/stop loss percentage set for {user.name}, {symbol} is {tp}% and {sl}% respectively. (-1 means not set)"
    )
    return ConversationHandler.END


def choose_platform(update: Update, context: CallbackContext):
    if not update.message.chat_id in current_users:
        update.message.reply_text("Please initalize with /start first.")
        return ConversationHandler.END
    update.message.reply_text(
        "Please choose the platform:\n1. AAX\n2. Bybit\n3.Binance\nPlease enter your choice (1,2,3)"
    )
    return SEP3


def change_api(update: Update, context: CallbackContext):
    platform = int(update.message.text)
    context.user_data["platform"] = platform
    if platform == 3:
        update.message.reply_text("Please provide your API Key from Binance.")
    elif platform == 2:
        update.message.reply_text("Please provide your API Key from Bybit.")
    else:
        update.message.reply_text("Please provide your API Key from AAX.")
    update.message.reply_text(
        "*SECURITY WARNING*\nTo ensure safety of funds, please note the following before providing your API key:\n1. Set up a new key for this program, don't reuse your other API keys.\n2. Restrict access to this IP: *35.229.163.161*\n3. Only allow these API Restrictions: 'Enable Reading' and 'Enable Futures'.",
        parse_mode=telegram.ParseMode.MARKDOWN,
    )
    return SEP1


def change_secret(update: Update, context: CallbackContext):
    user = current_users[update.message.chat_id]
    logger.info(f"User {user.uname} changing api keys.")
    if not update.message.text.isalnum():
        update.message.reply_text("Your API key is invalid, please enter again.")
        return SEP1
    update.message.reply_text(
        "Please provide your Secret Key.\n*DELETE YOUR MESSAGE IMMEDIATELY AFTERWARDS.*",
        parse_mode=telegram.ParseMode.MARKDOWN,
    )
    context.user_data["api_key"] = update.message.text
    return SEP2


piclock = threading.Lock()


def save_trading_pnl():
    while True:
        time.sleep(2 * 60)
        try:
            bal = current_stream.get_balance()
            if not bal is None:
                with open(f"calvinbot_pnlrecord.csv", "a") as f:
                    f.write(f"{str(bal)}\n")
        except:
            continue


def plotgraph(val, title):
    color = ["b", "g", "r", "c", "m", "k"]
    randomColor = color[random.randint(0, len(color) - 1)]
    # plt.ylim(math.floor(min(val) * 0.99), math.ceil(max(val)))
    # plt.autoscale(False)
    plt.plot(val, color=randomColor)
    plt.ylabel("USDT Balance")
    current = datetime.now() + timedelta(hours=8)
    plt.xlabel(f"Time (updated {current.strftime('%d/%m/%Y, %H:%M:%S')})")
    plt.title(title)
    plt.savefig("1.png")


def viewpnlstat(update: Update, context: CallbackContext):
    if not update.message.chat_id in current_users:
        update.message.reply_text("Please initalize with /start first.")
    user = current_users[update.message.chat_id]
    try:
        df = pd.read_csv(f"calvinbot_pnlrecord.csv", header=None)
    except:
        update.message.reply_text("No statistics yet.")
        return
    pastvalue = df.loc[:, 0].values
    if len(pastvalue) == 0:
        update.message.reply_text("No statistics yet.")
        return
    piclock.acquire()
    daily = 24 * 30
    p1 = Process(target=plotgraph, args=(pastvalue[-daily:], "Daily Balance",))
    p1.start()
    p1.join()
    time.sleep(0.1)
    with open("1.png", "rb") as f:
        updater.bot.sendPhoto(user.chat_id, f)
    weekly = 7 * 24 * 30
    p2 = Process(target=plotgraph, args=(pastvalue[-weekly:], "Weekly Balance",))
    p2.start()
    p2.join()
    time.sleep(0.1)
    with open("1.png", "rb") as f:
        updater.bot.sendPhoto(user.chat_id, f)
    monthly = 30 * 7 * 24 * 30
    p3 = Process(target=plotgraph, args=(pastvalue[-monthly:], "Monthly Balance",))
    p3.start()
    p3.join()
    time.sleep(0.1)
    with open("1.png", "rb") as f:
        updater.bot.sendPhoto(user.chat_id, f)
    piclock.release()
    return


def change_bnall(update: Update, context: CallbackContext):
    if not update.message.text.isalnum():
        update.message.reply_text("Your secret key is invalid, please enter again.")
        return SEP2
    user = current_users[update.message.chat_id]
    user.api_key = context.user_data["api_key"]
    user.api_secret = update.message.text
    if context.user_data["platform"] == 1:
        user.client = AAXClient(
            user.chat_id, user.uname, user.safety_ratio, user.api_key, user.api_secret
        )
    elif context.user_data["platform"] == 2:
        user.client = BybitClient(
            user.chat_id, user.uname, user.safety_ratio, user.api_key, user.api_secret
        )
    else:
        user.client = BinanceClient(
            user.chat_id, user.uname, user.safety_ratio, user.api_key, user.api_secret
        )
    user.reload()
    user.tplatform = context.user_data["platform"]
    update.message.reply_text(
        "Success! If you changed platforms, your proportions and leverages might be reset. Please change them back accordingly."
    )
    return ConversationHandler.END


def check_balance(update: Update, context: CallbackContext):
    if not update.message.chat_id in current_users:
        update.message.reply_text("Please initalize with /start first.")
    current_users[update.message.chat_id].client.get_balance()
    return


def close_position(update: Update, context: CallbackContext):
    if not update.message.chat_id in current_users:
        update.message.reply_text("Please initalize with /start first.")
        return ConversationHandler.END
    user = current_users[update.message.chat_id]
    listsymbols = user.client.get_symbols()
    listsymbols = [[x] for x in listsymbols]
    update.message.reply_text(
        "Please choose the symbol to close.",
        reply_markup=ReplyKeyboardMarkup(
            listsymbols, one_time_keyboard=True, input_field_placeholder="Which Symbol?"
        ),
    )
    return CP1


def conf_symbol(update: Update, context: CallbackContext):
    user = current_users[update.message.chat_id]
    listsymbols = user.client.get_symbols()
    if not update.message.text in listsymbols:
        listsymbols = [[x] for x in listsymbols]
        update.message.reply_text(
            "Your symbol is not valid! Please choose again.",
            reply_markup=ReplyKeyboardMarkup(
                listsymbols,
                one_time_keyboard=True,
                input_field_placeholder="Which Symbol?",
            ),
        )
        return CP1
    user.client.close_position(update.message.text)
    return ConversationHandler.END


class userClient:
    def __init__(
        self,
        chat_id,
        uname,
        safety_ratio,
        api_key,
        api_secret,
        proportion,
        positions=None,
        Leverage=None,
        tp=-1,
        sl=-1,
        lmode=0,
        tplatform=3,
    ):
        self.chat_id = chat_id
        self.uname = uname
        self.name = "CalvinTsai"
        self.api_key = api_key
        self.api_secret = api_secret
        self.tplatform = tplatform
        if self.tplatform == 1:
            self.client = AAXClient(chat_id, uname, safety_ratio, api_key, api_secret)
        elif self.tplatform == 2:
            self.client = BybitClient(chat_id, uname, safety_ratio, api_key, api_secret)
        else:
            self.client = BinanceClient(
                chat_id, uname, safety_ratio, api_key, api_secret
            )
        self.tpslids = {}
        # self.unfulfilledPos = {}  # Map Kevin's Client ID to own orderId
        self.safety_ratio = safety_ratio
        self.positions = positions
        self.tmodes = {}
        self.lmode = lmode
        self.needprop = False
        self.needlev = False
        if self.positions is None:
            self.positions = {}
        self.needtp = False
        self.needsl = False
        self.take_profit_percent = {}
        if isinstance(tp, int):
            self.needtp = True
        else:
            self.take_profit_percent = tp
        self.stop_loss_percent = {}
        if isinstance(sl, int):
            self.needsl = True
        else:
            self.stop_loss_percent = sl
        self.proportion = proportion
        self.leverage = Leverage
        if isinstance(self.proportion, float):
            self.proportion = {}
            self.needprop = True
        if self.leverage is None:
            self.leverage = {}
            self.needlev = True
        listSymbols = self.get_symbols()
        for symbol in listSymbols:
            if self.needprop:
                self.proportion[symbol] = proportion
            if self.needlev:
                self.leverage[symbol] = 2
            if self.needtp:
                self.take_profit_percent[symbol] = tp
            if self.needsl:
                self.stop_loss_percent[symbol] = sl
            self.tmodes[symbol] = 0

    def get_symbols(self):
        return self.client.get_symbols()

    def open_trade(self, df, isCloseAll):
        return self.client.open_trade(
            df,
            self.uname,
            self.proportion,
            self.leverage,
            self.lmode,
            self.tmodes,
            self.positions,
            self.take_profit_percent,
            self.stop_loss_percent,
            False,
            isCloseAll,
        )

    def reload(self):
        self.client.reload()
        symbollist = self.client.get_symbols()
        secondProportion = {}
        secondLeverage = {}
        secondtmodes = {}
        secondtp = {}
        secondsl = {}
        for symbol in symbollist:
            if (
                symbol in self.proportion
                and symbol in self.leverage
                and symbol in self.tmodes
                and symbol in self.take_profit_percent
                and symbol in self.stop_loss_percent
            ):
                secondProportion[symbol] = self.proportion[symbol]
                secondLeverage[symbol] = self.leverage[symbol]
                secondtmodes[symbol] = self.tmodes[symbol]
                secondtp[symbol] = self.take_profit_percent[symbol]
                secondsl[symbol] = self.stop_loss_percent[symbol]
            else:
                secondProportion[symbol] = 0
                secondLeverage[symbol] = 20
                secondtmodes[symbol] = 0
                secondtp[symbol] = -1
                secondsl[symbol] = -1
                updater.bot.sendMessage(
                    chat_id=self.chat_id,
                    text=f"Please note that there is a new symbol {symbol} available. You may want to adjust your settings for it.",
                )
        self.proportion = secondProportion
        self.leverage = secondLeverage
        self.tmodes = secondtmodes
        self.take_profit_percent = secondtp
        self.stop_loss_percent = secondsl
        return

    def change_safety_ratio(self, safety_ratio):
        logger.info(f"{self.uname} changed safety ratio.")
        self.safety_ratio = safety_ratio
        self.client.change_safety_ratio(safety_ratio)
        # updater.bot.sendMessage(
        #     chat_id=self.chat_id, text="Succesfully changed safety ratio."
        # )
        return

    def change_proportion(self, symbol, prop):
        if symbol not in self.proportion:
            updater.bot.sendMessage(
                chat_id=self.chat_id,
                text="Sorry,but this symbol is not available right now.",
            )
        self.proportion[symbol] = prop
        logger.info(f"{self.uname} Successfully changed proportion.")
        updater.bot.sendMessage(
            chat_id=self.chat_id, text=f"Successfully changed proportion!"
        )
        return

    def get_proportion(self, symbol):
        if symbol not in self.proportion:
            updater.bot.sendMessage(
                chat_id=self.chat_id,
                text="Sorry,but this symbol is not available right now.",
            )
            return
        # updater.bot.sendMessage(chat_id=self.chat_id,text=f"The proportion for {symbol} is {self.proportion[symbol]}x.")
        logger.info(f"{self.uname} Successfully queried proportion.")
        return self.proportion[symbol]

    def change_all_proportion(self, prop):
        self.reload()
        for symbol in self.proportion:
            self.proportion[symbol] = prop
        logger.info(f"{self.uname} Successfully changed all proportion.")
        updater.bot.sendMessage(
            chat_id=self.chat_id, text=f"Successfully changed proportion!"
        )
        return

    def change_leverage(self, symbol, lev):
        if symbol not in self.leverage:
            updater.bot.sendMessage(
                chat_id=self.chat_id,
                text="Sorry,but this symbol is not available right now.",
            )
        try:
            lev = int(lev)
            assert lev >= 1 and lev <= 125
        except:
            updater.bot.sendMessage(
                chat_id=self.chat_id,
                text="Sorry,but the leverage must be an integer between 1 and 125.",
            )
            return
        self.leverage[symbol] = lev
        logger.info(f"{self.uname} Successfully changed leverage.")
        updater.bot.sendMessage(
            chat_id=self.chat_id, text="Successfully changed leverage!"
        )
        return

    def get_leverage(self, symbol):
        if symbol not in self.leverage:
            updater.bot.sendMessage(
                chat_id=self.chat_id,
                text="Sorry,but this symbol is not available right now.",
            )
            return
        # updater.bot.sendMessage(chat_id=self.chat_id,text=f"The leverage for {symbol} is {self.leverage[symbol]}x.")
        logger.info(f"{self.uname} Successfully queried leverage.")
        return self.leverage[symbol]

    def change_all_leverage(self, lev):
        try:
            lev = int(lev)
            assert lev >= 1 and lev <= 125
        except:
            updater.bot.sendMessage(
                chat_id=self.chat_id,
                text="Sorry,but the leverage must be an integer between 1 and 125.",
            )
            return
        for symbol in self.leverage:
            self.leverage[symbol] = lev
        logger.info(f"{self.uname} Successfully changed all leverage.")
        updater.bot.sendMessage(
            chat_id=self.chat_id, text="Successfully changed leverage!"
        )
        return

    def get_tpsl(self, symbol):
        if symbol not in self.take_profit_percent:
            updater.bot.sendMessage(
                chat_id=self.chat_id,
                text="Sorry,but this symbol is not available right now.",
            )
            return
        # updater.bot.sendMessage(chat_id=self.chat_id,text=f"The leverage for {symbol} is {self.leverage[symbol]}x.")
        logger.info(f"{self.uname} Successfully queried profit/loss percentages.")
        return self.take_profit_percent[symbol], self.stop_loss_percent[symbol]

    def change_all_tpsl(self, tp, sl):
        self.reload()
        try:
            tp = int(tp)
            sl = int(sl)
            assert tp >= -1 and tp <= 400 and sl >= -1 and sl <= 400
        except:
            updater.bot.sendMessage(
                chat_id=self.chat_id,
                text="Sorry,but the profit and loss percentage must be an integer between 0 and 400, or -1 if you don't want to set.",
            )
            return
        for symbol in self.take_profit_percent:
            self.take_profit_percent[symbol] = tp
            self.stop_loss_percent[symbol] = sl
        logger.info(
            f"{self.uname} Successfully changed all take profit/stop loss percentages."
        )
        return

    def change_tpsl(self, symbol, tp, sl):
        if symbol not in self.take_profit_percent:
            updater.bot.sendMessage(
                chat_id=self.chat_id,
                text="Sorry,but this symbol is not available right now.",
            )
            return
        try:
            tp = int(tp)
            sl = int(sl)
            assert tp >= -1 and tp <= 400 and sl >= -1 and sl <= 400
        except:
            updater.bot.sendMessage(
                chat_id=self.chat_id,
                text="Sorry,but the profit and loss percentage must be an integer between 0 and 400, or -1 if you don't want to set.",
            )
            return
        self.take_profit_percent[symbol] = tp
        self.stop_loss_percent[symbol] = sl
        logger.info(f"{self.uname} Successfully changed profit/loss percentage.")
        # updater.bot.sendMessage(chat_id=self.chat_id,text="Successfully changed leverage mode!")
        return

    def change_lmode(self, lmode):
        try:
            lmode = int(lmode)
            assert lmode >= 0 and lmode <= 2
        except:
            updater.bot.sendMessage(
                chat_id=self.chat_id,
                text="Sorry,but the leverage mode must be an integer between 0 and 2.",
            )
            return
        self.lmode = lmode
        logger.info(f"{self.uname} Successfully changed lmode.")
        # updater.bot.sendMessage(chat_id=self.chat_id,text="Successfully changed leverage mode!")
        return

    def get_balance(self):
        return self.client.get_balance()


class Auth(requests.auth.AuthBase):
    def __init__(self, api_key, secret_key):
        self.api_key = api_key
        self.secret_key = secret_key

    def __call__(self, request):
        nonce = str(int(1000 * time.time()))
        strBody = request.body.decode() if request.body else ""
        message = nonce + ":" + request.method + request.path_url + (strBody or "")
        signature = hmac.new(
            self.secret_key.encode(), message.encode(), hashlib.sha256
        ).hexdigest()
        request.headers.update(
            {
                "X-ACCESS-NONCE": nonce,
                "X-ACCESS-KEY": self.api_key,
                "X-ACCESS-SIGN": signature,
            }
        )
        return request


class AAXClient:
    def __init__(self, chat_id, uname, safety_ratio, api_key, api_secret):
        self.auth = Auth(api_key, api_secret)
        self.chat_id = chat_id
        self.uname = uname
        self.stepsize = {}
        self.ticksize = {}
        self.safety_ratio = safety_ratio
        info = requests.get("https://api.aax.com/v2/instruments").json()
        self.isReloaded = False
        self.allPositions = {}
        for thing in info["data"]:
            if thing["type"] == "futures" and thing["quote"] == "USDT":
                self.ticksize[thing["symbol"]] = round(
                    -math.log(float(thing["tickSize"]), 10)
                )
                self.stepsize[thing["symbol"]] = float(thing["minQuantity"]) * float(
                    thing["multiplier"]
                )

    def get_symbols(self):
        symbolList = []
        for symbol in self.stepsize:
            symbolList.append(symbol)
        return symbolList

    def close_position(self, symbol):
        data = {"symbol": symbol}
        response = requests.post(
            "https://api.aax.com/v2/futures/position/close", json=data, auth=self.auth
        ).json()
        if response["message"] == "Success" or response["message"] == "fsuccess":
            updater.bot.sendMessage(chat_id=self.chat_id, text="Success!")
            current_users[self.chat_id].positions[symbol + "LONG"] = 0
            current_users[self.chat_id].positions[symbol + "SHORT"] = 0
        else:
            updater.bot.sendMessage(
                chat_id=self.chat_id, text=f"Error: f{response['message']}"
            )
        return

    def query_trade(
        self,
        orderId,
        symbol,
        positionKey,
        isOpen,
        uname,
        takeProfit,
        stopLoss,
        Leverage,
    ):  # ONLY to be run as thread
        numTries = 0
        time.sleep(1)
        response = ""
        executed_qty = 0
        while True:
            try:
                params = {"symbol": symbol, "orderID": orderId}
                response = requests.get(
                    "https://api.aax.com/v2/futures/orders",
                    params=params,
                    auth=self.auth,
                ).json()
                response = response["data"]["list"][0]
                if response["orderStatus"] == 3:
                    updater.bot.sendMessage(
                        chat_id=self.chat_id,
                        text=f"Order ID {orderId} ({positionKey}) fulfilled successfully.",
                    )
                    # ADD TO POSITION
                    if isOpen:
                        if positionKey in current_users[self.chat_id].positions:
                            current_users[self.chat_id].positions[positionKey] += float(
                                response["cumQty"]
                            )
                        else:
                            current_users[self.chat_id].threads[idx].positions[
                                positionKey
                            ] = float(response["cumQty"])
                    else:
                        if positionKey in current_users[self.chat_id].positions:
                            current_users[self.chat_id].positions[positionKey] -= float(
                                response["cumQty"]
                            )
                        else:
                            current_users[self.chat_id].positions[positionKey] = 0
                        if current_users[self.chat_id].positions[positionKey] < 0:
                            current_users[self.chat_id].positions[positionKey] = 0
                        # check positions thenn close all
                    logger.info(
                        f"DEBUG {self.uname} {positionKey}: {current_users[self.chat_id].positions[positionKey]}"
                    )
                    return
                elif response["orderStatus"] in [4, 5, 6, 10, 11]:
                    updater.bot.sendMessage(
                        chat_id=self.chat_id,
                        text=f"Order ID {orderId} ({positionKey}) is cancelled/rejected.\n{response['rejectReason']}",
                    )
                    return
                elif response["orderStatus"] == 2:
                    updatedQty = float(response["cumQty"]) - executed_qty
                    if isOpen:
                        if positionKey in current_users[self.chat_id].positions:
                            current_users[self.chat_id].positions[
                                positionKey
                            ] += updatedQty
                        else:
                            current_users[self.chat_id].positions[
                                positionKey
                            ] = updatedQty
                    else:
                        if positionKey in current_users[self.chat_id].positions:
                            current_users[self.chat_id].positions[positionKey] -= float(
                                response["cumQty"]
                            )
                        else:
                            current_users[self.chat_id].positions[positionKey] = 0
                    executed_qty = float(response["cumQty"])
            except:
                logger.error("some error.")
                pass
            if numTries >= 59:
                break
            time.sleep(60)
            numTries += 1
        if response != "" and response["orderStatus"] == 2:
            updater.bot.sendMessage(
                chat_id=self.chat_id,
                text=f"Order ID {orderId} ({positionKey}) is only partially filled. The rest will be cancelled.",
            )
            try:
                requests.delete(
                    "https://api.aax.com/v2/futures/orders/cancel/" + orderId,
                    auth=self.auth,
                )
            except:
                pass

        if response != "" and response["status"] == "NEW":
            updater.bot.sendMessage(
                chat_id=self.chat_id,
                text=f"Order ID {orderId} ({positionKey}) has not been filled. It will be cancelled.",
            )
            try:
                requests.delete(
                    "https://api.aax.com/v2/futures/orders/cancel/" + orderId,
                    auth=self.auth,
                )
            except:
                pass

    def open_trade(
        self,
        df,
        uname,
        proportion,
        leverage,
        lmode,
        tmodes,
        positions,
        takeProfit,
        stopLoss,
        mute,
        isCloseAll,
    ):
        try:
            self.reload()
        except:
            time.sleep(10)
        logger.info("DEBUG\n" + df.to_string())
        df = df.values
        i = -1
        for tradeinfo in df:
            i += 1
            tradeinfo[1] = tradeinfo[1] + "FP"
            isOpen = False
            types = tradeinfo[0].upper()
            balance, collateral, coin = 0, 0, ""
            if not tradeinfo[1] in proportion:
                updater.bot.sendMessage(
                    chat_id=self.chat_id,
                    text=f"This trade will not be executed since {tradeinfo[1]} is not a valid symbol.",
                )
                continue
            try:
                coin = "USDT"
                balance = self.get_balance(False)
                if tradeinfo[1][-6:-2] == "BUSD":
                    tradeinfo[1] = tradeinfo[1][:-6] + "USDTFP"
                    if not mute:
                        updater.bot.sendMessage(
                            chat_id=self.chat_id,
                            text="Our system only supports USDT. This trade will be executed in USDT instead of BUSD.",
                        )
            except:
                coin = "USDT"
                balance = "0"
            if balance is None:
                balance = 0
            balance = float(balance)
            if types[:4] == "OPEN":
                isOpen = True
                positionSide = types[4:]
                if positionSide == "LONG":
                    side = "BUY"
                else:
                    side = "SELL"
                if lmode != 2:
                    try:
                        data = {
                            "symbol": tradeinfo[1],
                            "leverage": leverage[tradeinfo[1]],
                        }
                        r = requests.post(
                            "https://api.aax.com/v2/futures/position/leverage",
                            json=data,
                            auth=self.auth,
                        ).json()
                        if r["message"] != "success":
                            logger.error(f"Error found: {r['message']}")
                    except:
                        pass
            else:
                positionSide = types[5:]
                if positionSide == "LONG":
                    side = "SELL"
                else:
                    side = "BUY"
            quant = abs(tradeinfo[2]) * proportion[tradeinfo[1]]
            checkKey = tradeinfo[1].upper() + positionSide
            if not isOpen and (
                (checkKey not in positions) or (positions[checkKey] < quant)
            ):
                if checkKey not in positions or positions[checkKey] == 0:
                    if not mute:
                        updater.bot.sendMessage(
                            chat_id=self.chat_id,
                            text=f"Close {checkKey}: This trade will not be executed because your opened positions with this trader is 0.",
                        )
                    continue
                elif positions[checkKey] < quant:
                    quant = min(positions[checkKey], quant)
                    if not mute:
                        updater.bot.sendMessage(
                            chat_id=self.chat_id,
                            text=f"Close {checkKey}: The trade quantity will be less than expected, because you don't have enough positions to close.",
                        )
            elif not isOpen and (isCloseAll[i] or quant / positions[checkKey] > 0.9):
                quant = max(positions[checkKey], quant)
            if quant == 0:
                if not mute:
                    updater.bot.sendMessage(
                        chat_id=self.chat_id,
                        text=f"{side} {checkKey}: This trade will not be executed because size = 0. Adjust proportion if you want to follow.",
                    )
                continue
            params = {"symbol": tradeinfo[1]}
            while True:
                try:
                    response = requests.get(
                        "https://api.aax.com/v2/market/markPrice", params=params
                    ).json()
                    latest_price = float(response["p"])
                    break
                except:
                    logger.error("Cannot get latest price.")
                    time.sleep(2)
            reqticksize = self.ticksize[tradeinfo[1]]
            reqstepsize = self.stepsize[tradeinfo[1]]
            quant = self.round_up(quant, reqstepsize)
            # print(quant, reqstepsize)
            collateral = (latest_price * quant * reqstepsize) / leverage[tradeinfo[1]]
            quant = str(quant)
            if isOpen:
                if not mute:
                    updater.bot.sendMessage(
                        chat_id=self.chat_id,
                        text=f"For the following trade, you will need {collateral:.3f}{coin} as collateral.",
                    )
                if collateral >= balance * self.safety_ratio:
                    if not mute:
                        updater.bot.sendMessage(
                            chat_id=self.chat_id,
                            text=f"WARNING: this trade will take up more than {self.safety_ratio} of your available balance. It will NOT be executed. Manage your risks accordingly and reduce proportion if necessary.",
                        )
                    continue
            if isinstance(tradeinfo[3], str):
                tradeinfo[3] = tradeinfo[3].replace(",", "")
            target_price = "{:0.0{}f}".format(float(tradeinfo[3]), reqticksize)
            if tmodes[tradeinfo[1]] == 0 or (tmodes[tradeinfo[1]] == 2 and not isOpen):
                try:
                    tosend = f"Trying to execute the following trade:\nSymbol: {tradeinfo[1]}\nSide: {side}\ntype: MARKET\nquantity: {quant}"
                    if not mute:
                        updater.bot.sendMessage(chat_id=self.chat_id, text=tosend)
                    # rvalue = self.client.futures_create_order(
                    #     symbol=tradeinfo[1],
                    #     side=side,
                    #     positionSide=positionSide,
                    #     type="MARKET",
                    #     quantity=quant,
                    # )
                    data = {
                        "orderType": "MARKET",
                        "symbol": tradeinfo[1],
                        "orderQty": quant,
                        "side": side,
                    }
                    response = requests.post(
                        "https://api.aax.com/v2/futures/orders",
                        json=data,
                        auth=self.auth,
                    ).json()
                    if response["message"] == "success":
                        logger.info(f"{self.uname} opened order.")
                    else:
                        logger.error(f"Error: {response['message']}")
                        continue
                    positionKey = tradeinfo[1] + positionSide
                    # print(response["data"]["orderID"])
                    t1 = threading.Thread(
                        target=self.query_trade,
                        args=(
                            response["data"]["orderID"],
                            tradeinfo[1],
                            positionKey,
                            isOpen,
                            uname,
                            takeProfit[tradeinfo[1]],
                            stopLoss[tradeinfo[1]],
                            leverage[tradeinfo[1]],
                        ),
                    )
                    t1.start()
                except:
                    logger.error("Error in processing request.")
            else:
                try:
                    target_price = float(target_price)
                    if positionSide == "LONG":
                        target_price = min(latest_price, target_price)
                    else:
                        target_price = max(latest_price, target_price)
                except:
                    pass
                target_price = "{:0.0{}f}".format(float(target_price), reqticksize)
                try:
                    tosend = f"Trying to execute the following trade:\nSymbol: {tradeinfo[1]}\nSide: {side}\ntype: LIMIT\nquantity: {quant}\nPrice: {target_price}"
                    if not mute:
                        updater.bot.sendMessage(chat_id=self.chat_id, text=tosend)
                    data = {
                        "orderType": "LIMIT",
                        "symbol": tradeinfo[1],
                        "orderQty": quant,
                        "price": target_price,
                        "side": side,
                    }
                    response = requests.post(
                        "https://api.aax.com/v2/futures/orders",
                        json=data,
                        auth=self.auth,
                    ).json()
                    if response["message"] == "success":
                        logger.info(f"{self.uname} opened order.")
                    else:
                        logger.error(f"Error: {response['message']}")
                        continue
                    positionKey = tradeinfo[1] + positionSide
                    t1 = threading.Thread(
                        target=self.query_trade,
                        args=(
                            response["data"]["orderID"],
                            tradeinfo[1],
                            positionKey,
                            isOpen,
                            uname,
                            takeProfit[tradeinfo[1]],
                            stopLoss[tradeinfo[1]],
                            leverage[tradeinfo[1]],
                        ),
                    )
                    t1.start()
                except:
                    logger.error("have error!!")

    def reload(self):
        if not self.isReloaded:
            secondticksize = {}
            secondstepsize = {}
            info = requests.get("https://api.aax.com/v2/instruments").json()
            for thing in info["data"]:
                if thing["type"] == "futures" and thing["quote"] == "USDT":
                    secondticksize[thing["symbol"]] = round(
                        -math.log(float(thing["tickSize"]), 10)
                    )
                    secondstepsize[thing["symbol"]] = float(
                        thing["minQuantity"]
                    ) * float(thing["multiplier"])
            self.ticksize = secondticksize
            self.stepsize = secondstepsize
            self.isReloaded = True
            t1 = threading.Thread(target=self.reset_reload)
            t1.start()

    def reset_reload(self):
        time.sleep(30)
        self.isReloaded = False

    def change_safety_ratio(self, safety_ratio):
        logger.info(f"{self.uname} changed safety ratio.")
        self.safety_ratio = safety_ratio
        updater.bot.sendMessage(
            chat_id=self.chat_id, text="Succesfully changed safety ratio."
        )
        return

    def get_balance(self, querymode=True):
        try:
            params = {"purseType": "FUTP"}
            response = requests.get(
                "https://api.aax.com/v2/account/balances", params=params, auth=self.auth
            ).json()
            for asset in response["data"]:
                if asset["currency"] == "USDT":
                    if querymode:
                        tosend = f"Your USDT account balance:\nAvailable: {asset['available']}\nLocked: {asset['unavailable']}"
                        updater.bot.sendMessage(chat_id=self.chat_id, text=tosend)
                    else:
                        return float(asset["available"])
        except:
            updater.bot.sendMessage(
                chat_id=self.chat_id, text="Unable to retrieve balance."
            )

    def round_up(self, quant, minsize):
        return math.ceil(quant / minsize)


class BybitClient:
    def __init__(self, chat_id, uname, safety_ratio, api_key, api_secret):
        self.client = bybit.bybit(test=False, api_key=api_key, api_secret=api_secret)
        self.chat_id = chat_id
        self.uname = uname
        self.stepsize = {}
        self.ticksize = {}
        self.safety_ratio = safety_ratio
        self.isReloaded = False
        res = self.client.Symbol.Symbol_get().result()[0]
        for symbol in res["result"]:
            if symbol["name"][-4:] == "USDT":
                self.ticksize[symbol["name"]] = round(
                    -math.log(float(symbol["price_filter"]["tick_size"]), 10)
                )
                self.stepsize[symbol["name"]] = round(
                    -math.log(float(symbol["lot_size_filter"]["qty_step"]), 10)
                )
        for symbol in self.ticksize:
            self.client.LinearPositions.LinearPositions_switchIsolated(
                symbol=symbol, is_isolated=False, buy_leverage=20, sell_leverage=20
            ).result()
            self.client.LinearPositions.LinearPositions_switchMode(
                symbol=symbol, tp_sl_mode="Partial"
            ).result()

    def get_symbols(self):
        symbolList = []
        for symbol in self.stepsize:
            symbolList.append(symbol)
        return symbolList

    def close_position(self, symbol):
        result = self.client.LinearPositions.LinearPositions_myPosition(
            symbol=symbol
        ).result()[0]
        for pos in result["result"]:
            if float(pos["free_qty"]) > 0:
                side = "Buy" if pos["side"] == "Sell" else "Buy"
                self.client.LinearOrder.LinearOrder_new(
                    side=side,
                    symbol=symbol,
                    order_type="Market",
                    qty=float(pos["free_qty"]),
                    time_in_force="GoodTillCancel",
                    reduce_only=True,
                    close_on_trigger=True,
                ).result()
        updater.bot.sendMessage(chat_id=self.chat_id, text="Success!")
        current_users[self.chat_id].positions[symbol + "LONG"] = 0
        current_users[self.chat_id].positions[symbol + "SHORT"] = 0
        return

    def tpsl_trade(
        self, symbol, side, qty, excprice, leverage, tp, sl, skey
    ):  # make sure everything in numbers not text//side: original side
        logger.info(f"Debug Check {leverage}/{tp}/{sl}")
        if side == "Buy":
            if tp != -1:
                tpPrice1 = excprice * (1 + (tp / leverage) / 100)
                qty1 = "{:0.0{}f}".format(qty, self.stepsize[symbol])
                tpPrice1 = "{:0.0{}f}".format(tpPrice1, self.ticksize[symbol])
                try:
                    result = self.client.LinearPositions.LinearPositions_tradingStop(
                        symbol=symbol,
                        side=side,
                        take_profit=float(tpPrice1),
                        tp_trigger_by="MarkPrice",
                        tp_size=float(qty1),
                    ).result()[0]
                    if result["ret_msg"] != "OK":
                        logger.error(f"Error in tpsl: {result['ret_msg']}")
                except:
                    logger.error("some error again")
            if sl != -1:
                tpPrice2 = excprice * (1 - (sl / leverage) / 100)
                qty2 = "{:0.0{}f}".format(qty, self.stepsize[symbol])
                tpPrice2 = "{:0.0{}f}".format(tpPrice2, self.ticksize[symbol])
                try:
                    result = self.client.LinearPositions.LinearPositions_tradingStop(
                        symbol=symbol,
                        side=side,
                        stop_loss=float(tpPrice2),
                        sl_trigger_by="MarkPrice",
                        sl_size=float(qty2),
                    ).result()[0]
                    if result["ret_msg"] != "OK":
                        logger.error(f"Error in tpsl: {result['ret_msg']}")
                except:
                    logger.error("SL error")
        else:
            if tp != -1:
                tpPrice1 = excprice * (1 - (tp / leverage) / 100)
                qty1 = "{:0.0{}f}".format(qty, self.stepsize[symbol])
                tpPrice1 = "{:0.0{}f}".format(tpPrice1, self.ticksize[symbol])
                try:
                    result = self.client.LinearPositions.LinearPositions_tradingStop(
                        symbol=symbol,
                        side=side,
                        take_profit=float(tpPrice1),
                        tp_trigger_by="MarkPrice",
                        tp_size=float(qty1),
                    ).result()[0]
                    if result["ret_msg"] != "OK":
                        logger.error(f"Error in tpsl: {result['ret_msg']}")
                except:
                    logger.error("some error again")
            if sl != -1:
                tpPrice2 = excprice * (1 + (sl / leverage) / 100)
                qty2 = "{:0.0{}f}".format(qty, self.stepsize[symbol])
                tpPrice2 = "{:0.0{}f}".format(tpPrice2, self.ticksize[symbol])
                try:
                    result = self.client.LinearPositions.LinearPositions_tradingStop(
                        symbol=symbol,
                        side=side,
                        stop_loss=float(tpPrice2),
                        sl_trigger_by="MarkPrice",
                        sl_size=float(qty2),
                    ).result()[0]
                    if result["ret_msg"] != "OK":
                        logger.error(f"Error in tpsl: {result['ret_msg']}")
                except:
                    logger.error("SL error")
        return

    def query_trade(
        self,
        orderId,
        symbol,
        positionKey,
        isOpen,
        uname,
        takeProfit,
        stopLoss,
        Leverage,
    ):  # ONLY to be run as thread
        numTries = 0
        time.sleep(1)
        result = ""
        executed_qty = 0
        while True:
            try:
                result = self.client.LinearOrder.LinearOrder_query(
                    symbol=symbol, order_id=orderId
                ).result()[0]
                if result["ret_msg"] != "OK":
                    logger.error("There is an error!")
                    return
                result = result["result"]
                if result["order_status"] == "Filled":
                    updater.bot.sendMessage(
                        chat_id=self.chat_id,
                        text=f"Order ID {orderId} ({positionKey}) fulfilled successfully.",
                    )
                    # ADD TO POSITION
                    if isOpen:
                        if positionKey in current_users[self.chat_id].positions:
                            current_users[self.chat_id].positions[positionKey] += float(
                                result["cum_exec_qty"]
                            )
                        else:
                            current_users[self.chat_id].positions[positionKey] = float(
                                result["cum_exec_qty"]
                            )
                        try:
                            self.tpsl_trade(
                                symbol,
                                result["side"],
                                float(result["cum_exec_qty"]),
                                float(result["last_exec_price"]),
                                Leverage,
                                takeProfit,
                                stopLoss,
                                positionKey,
                            )
                        except:
                            pass
                    else:
                        if positionKey in current_users[self.chat_id].positions:
                            current_users[self.chat_id].positions[positionKey] -= float(
                                result["cum_exec_qty"]
                            )
                        else:
                            current_users[self.chat_id].positions[positionKey] = 0
                        if current_users[self.chat_id].positions[positionKey] < 0:
                            current_users[self.chat_id].positions[positionKey] = 0
                        # check positions thenn close all
                        res = self.client.LinearPositions.LinearPositions_myPosition(
                            symbol=symbol
                        ).result()[0]["result"]
                        checkside = "Buy" if result["side"] == "Sell" else "Sell"
                        for pos in res:
                            logger.info(str(pos))
                            if pos["side"] == checkside and float(pos["size"]) == 0:
                                current_users[self.chat_id].positions[positionKey] = 0
                                break
                    logger.info(
                        f"DEBUG {self.uname} {positionKey}: {current_users[self.chat_id].positions[positionKey]}"
                    )
                    return
                elif result["order_status"] in [
                    "Rejected",
                    "PendingCancel",
                    "Cancelled",
                ]:
                    updater.bot.sendMessage(
                        chat_id=self.chat_id,
                        text=f"Order ID {orderId} ({positionKey}) is cancelled/rejected.",
                    )
                    return
                elif result["order_status"] == "PartiallyFilled":
                    updatedQty = float(result["cum_exec_qty"]) - executed_qty
                    if isOpen:
                        if positionKey in current_users[self.chat_id].positions:
                            current_users[self.chat_id].positions[
                                positionKey
                            ] += updatedQty
                        else:
                            current_users[self.chat_id].positions[
                                positionKey
                            ] = updatedQty
                    else:
                        if positionKey in current_users[self.chat_id].positions:
                            current_users[self.chat_id].positions[positionKey] -= float(
                                result["cum_exec_qty"]
                            )
                        else:
                            current_users[self.chat_id].positions[positionKey] = 0
                    executed_qty = float(result["cum_exec_qty"])
            except:
                logger.error("eeerrroooorrr")
                pass
            if numTries >= 59:
                break
            time.sleep(60)
            numTries += 1
        if result != "" and result["order_status"] == "PartiallyFilled":
            updater.bot.sendMessage(
                chat_id=self.chat_id,
                text=f"Order ID {orderId} ({positionKey}) is only partially filled. The rest will be cancelled.",
            )
            try:
                self.tpsl_trade(
                    symbol,
                    result["side"],
                    float(result["cum_exec_qty"]),
                    float(result["last_exec_price"]),
                    Leverage,
                    takeProfit,
                    stopLoss,
                    positionKey,
                )
                self.client.LinearOrder.LinearOrder_cancel(
                    symbol=symbol, order_id=orderId
                ).result()
            except:
                pass

        if result != "" and result["order_status"] == "New":
            updater.bot.sendMessage(
                chat_id=self.chat_id,
                text=f"Order ID {orderId} ({positionKey}) has not been filled. It will be cancelled.",
            )
            try:
                self.client.LinearOrder.LinearOrder_cancel(
                    symbol=symbol, order_id=orderId
                ).result()
            except:
                pass

    def open_trade(
        self,
        df,
        uname,
        proportion,
        leverage,
        lmode,
        tmodes,
        positions,
        takeProfit,
        stopLoss,
        mute,
        isCloseAll,
    ):

        try:
            self.reload()
        except:
            time.sleep(10)
        logger.info("DEBUG\n" + df.to_string())
        df = df.values
        i = -1
        for tradeinfo in df:
            i += 1
            isOpen = False
            types = tradeinfo[0].upper()
            balance, collateral, coin = 0, 0, ""
            if not tradeinfo[1] in proportion:
                updater.bot.sendMessage(
                    chat_id=self.chat_id,
                    text=f"This trade will not be executed since {tradeinfo[1]} is not a valid symbol.",
                )
                continue
            try:
                coin = "USDT"
                res = self.client.Wallet.Wallet_getBalance(coin=coin).result()[0][
                    "result"
                ]["USDT"]
                balance = res["available_balance"]
            except:
                coin = "USDT"
                balance = "0"
                logger.error("Cannot retrieve balance.")
            balance = float(balance)
            if types[:4] == "OPEN":
                isOpen = True
                positionSide = types[4:]
                if positionSide == "LONG":
                    side = "Buy"
                else:
                    side = "Sell"
                if lmode != 2:
                    try:
                        self.client.LinearPositions.LinearPositions_saveLeverage(
                            symbol=tradeinfo[1],
                            buy_leverage=str(leverage[tradeinfo[1]]),
                            sell_leverage=str(leverage[tradeinfo[1]]),
                        ).result()
                    except:
                        pass
            else:
                positionSide = types[5:]
                if positionSide == "LONG":
                    side = "Sell"
                else:
                    side = "Buy"
            quant = abs(tradeinfo[2]) * proportion[tradeinfo[1]]
            checkKey = tradeinfo[1].upper() + positionSide
            if not isOpen and (
                (checkKey not in positions) or (positions[checkKey] < quant)
            ):
                if checkKey not in positions or positions[checkKey] == 0:
                    if not mute:
                        updater.bot.sendMessage(
                            chat_id=self.chat_id,
                            text=f"Close {checkKey}: This trade will not be executed because your opened positions with this trader is 0.",
                        )
                    continue
                elif positions[checkKey] < quant:
                    quant = min(positions[checkKey], quant)
                    if not mute:
                        updater.bot.sendMessage(
                            chat_id=self.chat_id,
                            text=f"Close {checkKey}: The trade quantity will be less than expected, because you don't have enough positions to close.",
                        )
            elif not isOpen and (isCloseAll[i] or quant / positions[checkKey] > 0.9):
                quant = max(positions[checkKey], quant)
            if quant == 0:
                if not mute:
                    updater.bot.sendMessage(
                        chat_id=self.chat_id,
                        text=f"{side} {checkKey}: This trade will not be executed because size = 0. Adjust proportion if you want to follow.",
                    )
                continue
            latest_price = float(
                self.client.Market.Market_symbolInfo(symbol=tradeinfo[1]).result()[0][
                    "result"
                ][0]["mark_price"]
            )
            reqticksize = self.ticksize[tradeinfo[1]]
            reqstepsize = self.stepsize[tradeinfo[1]]
            quant = self.round_up(quant, reqstepsize)
            collateral = (latest_price * quant) / leverage[tradeinfo[1]]
            quant = str(quant)
            if isOpen:
                if not mute:
                    updater.bot.sendMessage(
                        chat_id=self.chat_id,
                        text=f"For the following trade, you will need {collateral:.3f}{coin} as collateral.",
                    )
                if collateral >= balance * self.safety_ratio:
                    if not mute:
                        updater.bot.sendMessage(
                            chat_id=self.chat_id,
                            text=f"WARNING: this trade will take up more than {self.safety_ratio} of your available balance. It will NOT be executed. Manage your risks accordingly and reduce proportion if necessary.",
                        )
                    continue
            if isinstance(tradeinfo[3], str):
                tradeinfo[3] = tradeinfo[3].replace(",", "")
            target_price = "{:0.0{}f}".format(float(tradeinfo[3]), reqticksize)
            if tmodes[tradeinfo[1]] == 0 or (tmodes[tradeinfo[1]] == 2 and not isOpen):
                try:
                    tosend = f"Trying to execute the following trade:\nSymbol: {tradeinfo[1]}\nSide: {side}\npositionSide: {positionSide}\ntype: MARKET\nquantity: {quant}"
                    if not mute:
                        updater.bot.sendMessage(chat_id=self.chat_id, text=tosend)
                    if isOpen:
                        response = self.client.LinearOrder.LinearOrder_new(
                            side=side,
                            symbol=tradeinfo[1],
                            order_type="Market",
                            qty=quant,
                            time_in_force="GoodTillCancel",
                            reduce_only=False,
                            close_on_trigger=False,
                        ).result()[0]
                    else:
                        response = self.client.LinearOrder.LinearOrder_new(
                            side=side,
                            symbol=tradeinfo[1],
                            order_type="Market",
                            qty=quant,
                            time_in_force="GoodTillCancel",
                            reduce_only=True,
                            close_on_trigger=True,
                        ).result()[0]
                    if response["ret_msg"] == "OK":
                        logger.info(f"{self.uname} opened order.")
                    else:
                        logger.error(f"Error: {response['ret_msg']}")
                        updater.bot.sendMessage(
                            chat_id=self.chat_id, text=f"Error: {response['ret_msg']}"
                        )
                        retmsg = response["ret_msg"]
                        if retmsg.find("reduce-only") != -1:
                            positionKey = tradeinfo[1] + positionSide
                            idx = current_users[self.chat_id].trader_names.index(uname)
                            current_users[self.chat_id].threads[idx].positions[
                                positionKey
                            ] = 0
                        continue
                    positionKey = tradeinfo[1] + positionSide
                    # print(response["result"]["order_id"])
                    t1 = threading.Thread(
                        target=self.query_trade,
                        args=(
                            response["result"]["order_id"],
                            tradeinfo[1],
                            positionKey,
                            isOpen,
                            uname,
                            takeProfit[tradeinfo[1]],
                            stopLoss[tradeinfo[1]],
                            leverage[tradeinfo[1]],
                        ),
                    )
                    t1.start()
                except:
                    logger.error("Error in processing request.")
            else:
                try:
                    target_price = float(target_price)
                    if positionSide == "LONG":
                        target_price = min(latest_price, target_price)
                    else:
                        target_price = max(latest_price, target_price)
                except:
                    pass
                target_price = "{:0.0{}f}".format(float(target_price), reqticksize)
                try:
                    tosend = f"Trying to execute the following trade:\nSymbol: {tradeinfo[1]}\nSide: {side}\ntype: LIMIT\nquantity: {quant}\nPrice: {target_price}"
                    if not mute:
                        updater.bot.sendMessage(chat_id=self.chat_id, text=tosend)
                    if isOpen:
                        response = self.client.LinearOrder.LinearOrder_new(
                            side=side,
                            symbol=tradeinfo[1],
                            order_type="Limit",
                            qty=quant,
                            price=target_price,
                            time_in_force="GoodTillCancel",
                            reduce_only=False,
                            close_on_trigger=False,
                        ).result()[0]
                    else:
                        response = self.client.LinearOrder.LinearOrder_new(
                            side=side,
                            symbol=tradeinfo[1],
                            order_type="Limit",
                            qty=quant,
                            price=target_price,
                            time_in_force="GoodTillCancel",
                            reduce_only=True,
                            close_on_trigger=True,
                        ).result()[0]
                    if response["ret_msg"] == "OK":
                        logger.info(f"{self.uname} opened order.")
                    else:
                        logger.error(f"Error: {response['ret_msg']}")
                        continue
                    positionKey = tradeinfo[1] + positionSide
                    t1 = threading.Thread(
                        target=self.query_trade,
                        args=(
                            response["result"]["order_id"],
                            tradeinfo[1],
                            positionKey,
                            isOpen,
                            uname,
                            takeProfit[tradeinfo[1]],
                            stopLoss[tradeinfo[1]],
                            leverage[tradeinfo[1]],
                        ),
                    )
                    t1.start()
                except:
                    logger.error("have error!!")

    def reload(self):
        if not self.isReloaded:
            secondticksize = {}
            secondstepsize = {}
            res = self.client.Symbol.Symbol_get().result()[0]
            for symbol in res["result"]:
                if symbol["name"][-4:] == "USDT":
                    secondticksize[symbol["name"]] = round(
                        -math.log(float(symbol["price_filter"]["tick_size"]), 10)
                    )
                    secondstepsize[symbol["name"]] = round(
                        -math.log(float(symbol["lot_size_filter"]["qty_step"]), 10)
                    )
            self.ticksize = secondticksize
            self.stepsize = secondstepsize
            self.isReloaded = True
            t1 = threading.Thread(target=self.reset_reload)
            t1.start()

    def reset_reload(self):
        time.sleep(30)
        self.isReloaded = False

    def change_safety_ratio(self, safety_ratio):
        logger.info(f"{self.uname} changed safety ratio.")
        self.safety_ratio = safety_ratio
        updater.bot.sendMessage(
            chat_id=self.chat_id, text="Succesfully changed safety ratio."
        )
        return

    def get_balance(self, querymode=True):
        try:
            result = self.client.Wallet.Wallet_getBalance(coin="USDT").result()
            result = result[0]["result"]["USDT"]
            if querymode:
                tosend = f"Your USDT account balance:\nBalance: {result['equity']}\nAvailable: {result['available_balance']}\nRealised PNL: {result['realised_pnl']}\nUnrealized PNL: {result['unrealised_pnl']}"
                updater.bot.sendMessage(chat_id=self.chat_id, text=tosend)
            else:
                return float(result["available_balance"])
        except:
            updater.bot.sendMessage(
                chat_id=self.chat_id, text="Unable to retrieve balance."
            )

    def round_up(self, n, decimals=0):
        multiplier = 10 ** decimals
        return math.ceil(n * multiplier) / multiplier


class BinanceClient:
    def __init__(self, chat_id, uname, safety_ratio, api_key, api_secret):
        self.client = Client(api_key, api_secret)
        self.chat_id = chat_id
        self.uname = uname
        self.stepsize = {}
        self.ticksize = {}
        self.safety_ratio = safety_ratio
        info = self.client.futures_exchange_info()
        self.isReloaded = False
        try:
            self.client.futures_change_position_mode(dualSidePosition=True)
        except BinanceAPIException as e:
            logger.error(e)
        for thing in info["symbols"]:
            self.ticksize[thing["symbol"]] = round(
                -math.log(float(thing["filters"][0]["tickSize"]), 10)
            )
            self.stepsize[thing["symbol"]] = round(
                -math.log(float(thing["filters"][1]["stepSize"]), 10)
            )
        try:
            for symbol in self.ticksize:
                self.client.futures_change_margin_type(
                    symbol=symbol, marginType="CROSSED"
                )
        except BinanceAPIException as e:
            logger.error(e)

    def get_symbols(self):
        symbolList = []
        for symbol in self.stepsize:
            symbolList.append(symbol)
        return symbolList

    def tpsl_trade(
        self, symbol, side, positionSide, qty, excprice, leverage, tp, sl
    ):  # make sure everything in numbers not text//side: original side
        side = "BUY" if side == "SELL" else "SELL"
        logger.info(f"Debug Check {leverage}/{tp}/{sl}")
        if positionSide == "LONG":
            if tp != -1:
                tpPrice1 = excprice * (1 + (tp / leverage) / 100)
                qty1 = "{:0.0{}f}".format(qty, self.stepsize[symbol])
                tpPrice1 = "{:0.0{}f}".format(tpPrice1, self.ticksize[symbol])
                try:
                    result = self.client.futures_create_order(
                        symbol=symbol,
                        side=side,
                        positionSide=positionSide,
                        type="TAKE_PROFIT_MARKET",
                        stopPrice=tpPrice1,
                        workingType="MARK_PRICE",
                        quantity=qty1,
                    )
                    skey = symbol + positionSide
                    if skey in current_users[self.chat_id].tpslids:
                        current_users[self.chat_id].tpslids[skey].append(
                            result["orderId"]
                        )
                    else:
                        current_users[self.chat_id].tpslids[skey] = []
                        current_users[self.chat_id].tpslids[skey].append(
                            result["orderId"]
                        )
                except BinanceAPIException as e:
                    logger.error(e)
                    updater.bot.sendMessage(chat_id=self.chat_id, text=str(e))
            if sl != -1:
                tpPrice2 = excprice * (1 - (sl / leverage) / 100)
                qty2 = "{:0.0{}f}".format(qty, self.stepsize[symbol])
                tpPrice2 = "{:0.0{}f}".format(tpPrice2, self.ticksize[symbol])
                try:
                    result = self.client.futures_create_order(
                        symbol=symbol,
                        side=side,
                        positionSide=positionSide,
                        type="STOP_MARKET",
                        stopPrice=tpPrice2,
                        workingType="MARK_PRICE",
                        quantity=qty2,
                    )
                    skey = symbol + positionSide
                    if skey in current_users[self.chat_id].tpslids:
                        current_users[self.chat_id].tpslids[skey].append(
                            result["orderId"]
                        )
                    else:
                        current_users[self.chat_id].tpslids[skey] = []
                        current_users[self.chat_id].tpslids[skey].append(
                            result["orderId"]
                        )
                except BinanceAPIException as e:
                    logger.error(e)
                    updater.bot.sendMessage(chat_id=self.chat_id, text=str(e))
        else:
            if tp != -1:
                tpPrice1 = excprice * (1 - (tp / leverage) / 100)
                qty1 = "{:0.0{}f}".format(qty, self.stepsize[symbol])
                tpPrice1 = "{:0.0{}f}".format(tpPrice1, self.ticksize[symbol])
                try:
                    result = self.client.futures_create_order(
                        symbol=symbol,
                        side=side,
                        positionSide=positionSide,
                        type="TAKE_PROFIT_MARKET",
                        stopPrice=tpPrice1,
                        workingType="MARK_PRICE",
                        quantity=qty1,
                    )
                    skey = symbol + positionSide
                    if skey in current_users[self.chat_id].tpslids:
                        current_users[self.chat_id].tpslids[skey].append(
                            result["orderId"]
                        )
                    else:
                        current_users[self.chat_id].tpslids[skey] = []
                        current_users[self.chat_id].tpslids[skey].append(
                            result["orderId"]
                        )
                except BinanceAPIException as e:
                    logger.error(e)
                    updater.bot.sendMessage(chat_id=self.chat_id, text=str(e))
            if sl != -1:
                tpPrice2 = excprice * (1 + (sl / leverage) / 100)
                qty2 = "{:0.0{}f}".format(qty, self.stepsize[symbol])
                tpPrice2 = "{:0.0{}f}".format(tpPrice2, self.ticksize[symbol])
                try:
                    result = self.client.futures_create_order(
                        symbol=symbol,
                        side=side,
                        positionSide=positionSide,
                        type="STOP_MARKET",
                        stopPrice=tpPrice2,
                        workingType="MARK_PRICE",
                        quantity=qty2,
                    )
                    skey = symbol + positionSide
                    if skey in current_users[self.chat_id].tpslids:
                        current_users[self.chat_id].tpslids[skey].append(
                            result["orderId"]
                        )
                    else:
                        current_users[self.chat_id].tpslids[skey] = []
                        current_users[self.chat_id].tpslids[skey].append(
                            result["orderId"]
                        )
                except BinanceAPIException as e:
                    logger.error(e)
                    updater.bot.sendMessage(chat_id=self.chat_id, text=str(e))
        return

    def query_trade(
        self,
        orderId,
        symbol,
        positionKey,
        isOpen,
        uname,
        takeProfit,
        stopLoss,
        Leverage,
    ):  # ONLY to be run as thread
        numTries = 0
        time.sleep(1)
        result = ""
        executed_qty = 0
        while True:
            try:
                result = self.client.futures_get_order(symbol=symbol, orderId=orderId)
                if result["status"] == "FILLED":
                    updater.bot.sendMessage(
                        chat_id=self.chat_id,
                        text=f"Order ID {orderId} ({positionKey}) fulfilled successfully.",
                    )
                    # ADD TO POSITION
                    if isOpen:
                        if positionKey in current_users[self.chat_id].positions:
                            current_users[self.chat_id].positions[positionKey] += float(
                                result["executedQty"]
                            )
                        else:
                            current_users[self.chat_id].positions[positionKey] = float(
                                result["executedQty"]
                            )
                        try:
                            self.tpsl_trade(
                                symbol,
                                result["side"],
                                result["positionSide"],
                                float(result["executedQty"]),
                                float(result["avgPrice"]),
                                Leverage,
                                takeProfit,
                                stopLoss,
                            )
                        except:
                            pass
                    else:
                        if positionKey in current_users[self.chat_id].positions:
                            current_users[self.chat_id].positions[positionKey] -= float(
                                result["executedQty"]
                            )
                        else:
                            current_users[self.chat_id].positions[positionKey] = 0
                        if current_users[self.chat_id].positions[positionKey] < 0:
                            current_users[self.chat_id].positions[positionKey] = 0
                        # check positions thenn close all
                        res = self.client.futures_position_information(symbol=symbol)
                        for pos in res:
                            logger.info(str(pos))
                            if (
                                pos["positionSide"] == result["positionSide"]
                                and float(pos["positionAmt"]) == 0
                            ):
                                if positionKey in current_users[self.chat_id].tpslids:
                                    idlist = current_users[self.chat_id].tpslids[
                                        positionKey
                                    ]
                                    try:
                                        for id in idlist:
                                            self.client.futures_cancel_order(
                                                symbol=symbol, orderId=id
                                            )
                                        current_users[self.chat_id].tpslids[
                                            positionKey
                                        ] = []
                                    except BinanceAPIException as e:
                                        logger.error(str(e))
                                current_users[self.chat_id].positions[positionKey] = 0
                    logger.info(
                        f"DEBUG {self.uname} {positionKey}: {current_users[self.chat_id].positions[positionKey]}"
                    )
                    return
                elif result["status"] in [
                    "CANCELED",
                    "PENDING_CANCEL",
                    "REJECTED",
                    "EXPIRED",
                ]:
                    updater.bot.sendMessage(
                        chat_id=self.chat_id,
                        text=f"Order ID {orderId} ({positionKey}) is cancelled/rejected.",
                    )
                    return
                elif result["status"] == "PARTIALLY_FILLED":
                    updatedQty = float(result["executedQty"]) - executed_qty
                    if isOpen:
                        if positionKey in current_users[self.chat_id].positions:
                            current_users[self.chat_id].positions[
                                positionKey
                            ] += updatedQty
                        else:
                            current_users[self.chat_id].positions[
                                positionKey
                            ] = updatedQty
                    else:
                        if positionKey in current_users[self.chat_id].positions:
                            current_users[self.chat_id].positions[positionKey] -= float(
                                result["executedQty"]
                            )
                        else:
                            current_users[self.chat_id].positions[positionKey] = 0
                    executed_qty = float(result["executedQty"])
            except BinanceAPIException as e:
                logger.error(e)
                pass
            if numTries >= 59:
                break
            time.sleep(60)
            numTries += 1
        if result != "" and result["status"] == "PARTIALLY_FILLED":
            updater.bot.sendMessage(
                chat_id=self.chat_id,
                text=f"Order ID {orderId} ({positionKey}) is only partially filled. The rest will be cancelled.",
            )
            try:
                self.tpsl_trade(
                    symbol,
                    result["side"],
                    result["positionSide"],
                    float(result["executedQty"]),
                    float(result["avgPrice"]),
                    Leverage,
                    takeProfit,
                    stopLoss,
                )
                self.client.futures_cancel_order(symbol=symbol, orderId=orderId)
            except:
                pass

        if result != "" and result["status"] == "NEW":
            updater.bot.sendMessage(
                chat_id=self.chat_id,
                text=f"Order ID {orderId} ({positionKey}) has not been filled. It will be cancelled.",
            )
            try:
                self.client.futures_cancel_order(symbol=symbol, orderId=orderId)
            except:
                pass

    def open_trade(
        self,
        df,
        uname,
        proportion,
        leverage,
        lmode,
        tmodes,
        positions,
        takeProfit,
        stopLoss,
        mute,
        isCloseAll,
    ):
        try:
            self.reload()
        except:
            time.sleep(10)
        logger.info("DEBUG\n" + df.to_string())
        df = df.values
        i = -1
        for tradeinfo in df:
            i += 1
            isOpen = False
            types = tradeinfo[0].upper()
            balance, collateral, coin = 0, 0, ""
            try:
                coin = "USDT"
                for asset in self.client.futures_account()["assets"]:
                    if asset["asset"] == "USDT":
                        balance = asset["maxWithdrawAmount"]
                        break
                if tradeinfo[1][-4:] == "BUSD":
                    tradeinfo[1] = tradeinfo[1][:-4] + "USDT"
                    if not mute:
                        updater.bot.sendMessage(
                            chat_id=self.chat_id,
                            text="Our system only supports USDT. This trade will be executed in USDT instead of BUSD.",
                        )
            except BinanceAPIException as e:
                coin = "USDT"
                balance = "0"
                logger.error(e)
            balance = float(balance)
            if types[:4] == "OPEN":
                isOpen = True
                positionSide = types[4:]
                if positionSide == "LONG":
                    side = "BUY"
                else:
                    side = "SELL"
                if lmode != 2:
                    try:
                        self.client.futures_change_leverage(
                            symbol=tradeinfo[1], leverage=leverage[tradeinfo[1]]
                        )
                    except:
                        pass
            else:
                positionSide = types[5:]
                if positionSide == "LONG":
                    side = "SELL"
                else:
                    side = "BUY"
            if not tradeinfo[1] in proportion:
                updater.bot.sendMessage(
                    chat_id=self.chat_id,
                    text=f"This trade will not be executed since {tradeinfo[1]} is not a valid symbol. If this is a new symbol, set your proportions first.",
                )
                continue
            quant = abs(tradeinfo[2]) * proportion[tradeinfo[1]]
            checkKey = tradeinfo[1].upper() + positionSide
            if not isOpen and (
                (checkKey not in positions) or (positions[checkKey] < quant)
            ):
                if checkKey not in positions or positions[checkKey] == 0:
                    if not mute:
                        updater.bot.sendMessage(
                            chat_id=self.chat_id,
                            text=f"Close {checkKey}: This trade will not be executed because your opened positions with this trader is 0.",
                        )
                    continue
                elif positions[checkKey] < quant:
                    quant = min(positions[checkKey], quant)
                    if not mute:
                        updater.bot.sendMessage(
                            chat_id=self.chat_id,
                            text=f"Close {checkKey}: The trade quantity will be less than expected, because you don't have enough positions to close.",
                        )
            elif not isOpen and (isCloseAll[i] or quant / positions[checkKey] > 0.9):
                quant = max(positions[checkKey], quant)
            if quant == 0:
                if not mute:
                    updater.bot.sendMessage(
                        chat_id=self.chat_id,
                        text=f"{side} {checkKey}: This trade will not be executed because size = 0. Adjust proportion if you want to follow.",
                    )
                continue
            latest_price = float(
                self.client.futures_mark_price(symbol=tradeinfo[1])["markPrice"]
            )
            reqticksize = self.ticksize[tradeinfo[1]]
            reqstepsize = self.stepsize[tradeinfo[1]]
            quant = self.round_up(quant, reqstepsize)
            collateral = (latest_price * quant) / leverage[tradeinfo[1]]
            quant = str(quant)
            if isOpen:
                if not mute:
                    updater.bot.sendMessage(
                        chat_id=self.chat_id,
                        text=f"For the following trade, you will need {collateral:.3f}{coin} as collateral.",
                    )
                if collateral >= balance * self.safety_ratio:
                    if not mute:
                        updater.bot.sendMessage(
                            chat_id=self.chat_id,
                            text=f"WARNING: this trade will take up more than {self.safety_ratio} of your available balance. It will NOT be executed. Manage your risks accordingly and reduce proportion if necessary.",
                        )
                    continue
            if isinstance(tradeinfo[3], str):
                tradeinfo[3] = tradeinfo[3].replace(",", "")
            target_price = "{:0.0{}f}".format(float(tradeinfo[3]), reqticksize)
            if tmodes[tradeinfo[1]] == 0 or (tmodes[tradeinfo[1]] == 2 and not isOpen):
                try:
                    tosend = f"Trying to execute the following trade:\nSymbol: {tradeinfo[1]}\nSide: {side}\npositionSide: {positionSide}\ntype: MARKET\nquantity: {quant}"
                    if not mute:
                        updater.bot.sendMessage(chat_id=self.chat_id, text=tosend)
                    rvalue = self.client.futures_create_order(
                        symbol=tradeinfo[1],
                        side=side,
                        positionSide=positionSide,
                        type="MARKET",
                        quantity=quant,
                    )
                    logger.info(f"{self.uname} opened order.")
                    positionKey = tradeinfo[1] + positionSide
                    t1 = threading.Thread(
                        target=self.query_trade,
                        args=(
                            rvalue["orderId"],
                            tradeinfo[1],
                            positionKey,
                            isOpen,
                            uname,
                            takeProfit[tradeinfo[1]],
                            stopLoss[tradeinfo[1]],
                            leverage[tradeinfo[1]],
                        ),
                    )
                    t1.start()
                except BinanceAPIException as e:
                    logger.error(e)
                    updater.bot.sendMessage(chat_id=self.chat_id, text=str(e))
                    if not isOpen and str(e).find("2022") >= 0:
                        positionKey = tradeinfo[1] + positionSide
                        current_users[self.chat_id].positions[positionKey] = 0
                        res = self.client.futures_position_information(
                            symbol=tradeinfo[1]
                        )
                        for pos in res:
                            if (
                                pos["positionSide"] == positionSide
                                and float(pos["positionAmt"]) == 0
                            ):
                                if positionKey in current_users[self.chat_id].tpslids:
                                    idlist = current_users[self.chat_id].tpslids[
                                        positionKey
                                    ]
                                    try:
                                        for id in idlist:
                                            self.client.futures_cancel_order(
                                                symbol=tradeinfo[1], orderId=id
                                            )
                                        logger.info(
                                            f"{tradeinfo[1]} tpsl order cancelled!"
                                        )
                                        current_users[self.chat_id].tpslids[
                                            positionKey
                                        ] = []
                                    except BinanceAPIException as e2:
                                        logger.error(str(e2))
            else:
                try:
                    target_price = float(target_price)
                    if positionSide == "LONG":
                        target_price = min(latest_price, target_price)
                    else:
                        target_price = max(latest_price, target_price)
                except:
                    pass
                target_price = "{:0.0{}f}".format(float(target_price), reqticksize)
                try:
                    tosend = f"Trying to execute the following trade:\nSymbol: {tradeinfo[1]}\nSide: {side}\npositionSide: {positionSide}\ntype: LIMIT\nquantity: {quant}\nPrice: {target_price}"
                    if not mute:
                        updater.bot.sendMessage(chat_id=self.chat_id, text=tosend)
                    rvalue = self.client.futures_create_order(
                        symbol=tradeinfo[1],
                        side=side,
                        positionSide=positionSide,
                        type="LIMIT",
                        quantity=quant,
                        price=target_price,
                        timeInForce="GTC",
                    )
                    logger.info(f"{self.uname} opened order.")
                    positionKey = tradeinfo[1] + positionSide
                    t1 = threading.Thread(
                        target=self.query_trade,
                        args=(
                            rvalue["orderId"],
                            tradeinfo[1],
                            positionKey,
                            isOpen,
                            uname,
                            takeProfit[tradeinfo[1]],
                            stopLoss[tradeinfo[1]],
                            leverage[tradeinfo[1]],
                        ),
                    )
                    t1.start()
                except BinanceAPIException as e:
                    logger.error(e)
                    updater.bot.sendMessage(chat_id=self.chat_id, text=str(e))

    def reload(self):
        if not self.isReloaded:
            info = self.client.futures_exchange_info()
            secondticksize = {}
            secondstepsize = {}
            for thing in info["symbols"]:
                secondticksize[thing["symbol"]] = round(
                    -math.log(float(thing["filters"][0]["tickSize"]), 10)
                )
                secondstepsize[thing["symbol"]] = round(
                    -math.log(float(thing["filters"][1]["stepSize"]), 10)
                )
            self.ticksize = secondticksize
            self.stepsize = secondstepsize
            self.isReloaded = True
            t1 = threading.Thread(target=self.reset_reload)
            t1.start()

    def round_up(self, n, decimals=0):
        multiplier = 10 ** decimals
        return math.ceil(n * multiplier) / multiplier

    def reset_reload(self):
        time.sleep(30)
        self.isReloaded = False

    def change_safety_ratio(self, safety_ratio):
        logger.info(f"{self.uname} changed safety ratio.")
        self.safety_ratio = safety_ratio

        updater.bot.sendMessage(
            chat_id=self.chat_id, text="Successfully changed safety ratio."
        )
        return

    def get_balance(self):
        try:
            result = self.client.futures_account()["assets"]
            for asset in result:
                if asset["asset"] == "USDT":
                    tosend = f"Your USDT account balance:\nBalance: {asset['walletBalance']}\nUnrealized PNL: {asset['unrealizedProfit']}\nMargin balance: {asset['marginBalance']}\nMax withdrawal balance: {asset['maxWithdrawAmount']}"
                    updater.bot.sendMessage(chat_id=self.chat_id, text=tosend)
        except BinanceAPIException as e:
            updater.bot.sendMessage(chat_id=self.chat_id, text=str(e))

    def close_position(self, symbol):
        updater.bot.sendMessage(
            chat_id=self.chat_id,
            text="This function is not implemented in the Binance client.",
        )
        return


def restore_save_data():
    logger.info("Restored data")
    with open("userdata_calvin.pickle", "rb") as f:
        userdata = pickle.load(f)
    for (
        x
    ) in (
        userdata
    ):  # (self,chat_id,uname,safety_ratio,api_key,api_secret,proportion,positions=None,Leverage=None,tp=-1,sl=-1,lmode=0):
        current_users[x["chat_id"]] = userClient(
            x["chat_id"],
            x["uname"],
            x["safety_ratio"],
            x["api_key"],
            x["api_secret"],
            x["proportion"],
            x["positions"],
            x["leverage"],
            x["tp"],
            x["sl"],
            x["lmode"],
            x["platform"],
        )


def reload_announcement():
    position = current_stream.lastPositions
    for user in current_users:
        user = current_users[user]
        updater.bot.sendMessage(
            user.chat_id, "The bot just got reloaded. Latest position:"
        )
        updater.bot.sendMessage(user.chat_id, position.to_string())


def error_callback(update, context):
    logger.error("Error!!!!!Why!!!")
    current_stream.pause()
    global is_reloading
    time.sleep(5)
    save_to_file(None, None)
    global reloading
    reloading = True
    global current_users
    for user in current_users:
        user = current_users[user]
        updater.bot.sendMessage(chat_id=user.chat_id, text="Automatic reloading...")
    current_users = {}
    logger.info("Everyone's service has ended.")
    if not is_reloading:
        t1 = threading.Thread(target=reload_updater)
        t1.start()
        is_reloading = True


def reload_updater():
    global updater
    global reloading
    global is_reloading
    updater.stop()
    updater.is_idle = False
    time.sleep(2)
    updater2 = Updater(cnt.bot_token2)
    dispatcher = updater2.dispatcher
    # Add conversation handler with the states GENDER, PHOTO, LOCATION and BIO
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            AUTH: [MessageHandler(Filters.text & ~Filters.command, auth_check)],
            DISCLAIMER: [MessageHandler(Filters.regex("^(yes)$"), disclaimer_check)],
            PLATFORM: [
                MessageHandler(Filters.regex("^(1|2|3)$"), check_platform)
            ],  # DO COME BACK
            APIKEY: [MessageHandler(Filters.text & ~Filters.command, check_api)],
            APISECRET: [MessageHandler(Filters.text & ~Filters.command, check_secret)],
            CHECKPROP: [MessageHandler(Filters.text & ~Filters.command, check_ratio)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    conv_handler2 = ConversationHandler(
        entry_points=[CommandHandler("admin", admin)],
        states={
            AUTH2: [MessageHandler(Filters.text & ~Filters.command, auth_check2)],
            ANNOUNCE: [
                MessageHandler(Filters.text & ~Filters.command, announce),
                CommandHandler("save", save_to_file),
                CommandHandler("endall", end_everyone),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    conv_handler6 = ConversationHandler(
        entry_points=[CommandHandler("setallleverage", setAllLeverage)],
        states={
            REALSETLEV: [
                MessageHandler(Filters.text & ~Filters.command, setAllLeverageReal)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    conv_handler7 = ConversationHandler(
        entry_points=[CommandHandler("setleverage", set_leverage)],
        states={
            LEVTRADER: [
                MessageHandler(Filters.text & ~Filters.command, leverage_choosesymbol)
            ],
            REALSETLEV2: [
                MessageHandler(Filters.text & ~Filters.command, setLeverageReal)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    conv_handler8 = ConversationHandler(
        entry_points=[CommandHandler("setallproportion", set_all_proportion)],
        states={
            ALLPROP: [
                MessageHandler(Filters.text & ~Filters.command, setAllProportionReal)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    conv_handler9 = ConversationHandler(
        entry_points=[CommandHandler("setproportion", set_proportion)],
        states={
            PROPSYM: [
                MessageHandler(Filters.text & ~Filters.command, proportion_choosesymbol)
            ],
            REALSETPROP2: [
                MessageHandler(Filters.text & ~Filters.command, setProportionReal)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    conv_handler10 = ConversationHandler(
        entry_points=[CommandHandler("getleverage", get_leverage)],
        states={
            REALSETLEV3: [
                MessageHandler(Filters.text & ~Filters.command, getLeverageReal)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    conv_handler11 = ConversationHandler(
        entry_points=[CommandHandler("getproportion", get_proportion)],
        states={
            REALSETLEV4: [
                MessageHandler(Filters.text & ~Filters.command, getproportionReal)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    conv_handler12 = ConversationHandler(
        entry_points=[CommandHandler("end", end_all)],
        states={COCO: [MessageHandler(Filters.regex("^(yes)$"), realEndAll)],},
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    # conv_handler13 = ConversationHandler(
    #     entry_points=[CommandHandler('settmode',set_omode)],
    #     states={
    #         PROPSYM2:[MessageHandler(Filters.text & ~Filters.command,omode_choosesymbol)],
    #         REALSETPROP3:[MessageHandler(Filters.regex('^(0|1|2)$'),setomodeReal)],
    #     },
    #     fallbacks=[CommandHandler('cancel', cancel)],
    # )
    conv_handler14 = ConversationHandler(
        entry_points=[CommandHandler("setlmode", set_lmode)],
        states={REALSETLEV5: [MessageHandler(Filters.regex("^(0|1)$"), setlmodeReal)],},
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    # conv_handler15 = ConversationHandler(
    #     entry_points=[CommandHandler('setalltmode',set_allomode)],
    #     states={
    #         REALSETLEV6:[MessageHandler(Filters.regex('^(0|1|2)$'),setallomodeReal)],
    #     },
    #     fallbacks=[CommandHandler('cancel', cancel)],
    # )
    conv_handler16 = ConversationHandler(
        entry_points=[CommandHandler("changesr", change_safetyratio)],
        states={
            LEVTRADER6: [
                MessageHandler(Filters.text & ~Filters.command, confirm_changesafety)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    conv_handler17 = ConversationHandler(
        entry_points=[CommandHandler("setalltpsl", set_all_tpsl)],
        states={
            REALSETPROP4: [
                MessageHandler(Filters.text & ~Filters.command, setAllTpslReal)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    conv_handler18 = ConversationHandler(
        entry_points=[CommandHandler("settpsl", set_tpsl)],
        states={
            PROPSYM3: [
                MessageHandler(Filters.text & ~Filters.command, tpsl_choosesymbol)
            ],
            REALSETPROP5: [
                MessageHandler(Filters.text & ~Filters.command, setTpslReal)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    conv_handler19 = ConversationHandler(
        entry_points=[CommandHandler("gettpsl", get_tpsl)],
        states={
            REALSETLEV7: [MessageHandler(Filters.text & ~Filters.command, getTpslReal)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    conv_handler22 = ConversationHandler(
        entry_points=[CommandHandler("changeapi", choose_platform)],
        states={
            SEP3: [MessageHandler(Filters.regex("^(1|2|3)$"), change_api)],
            SEP1: [MessageHandler(Filters.text & ~Filters.command, change_secret)],
            SEP2: [MessageHandler(Filters.text & ~Filters.command, change_bnall)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    conv_handler23 = ConversationHandler(
        entry_points=[CommandHandler("closeposition", close_position)],
        states={CP1: [MessageHandler(Filters.text & ~Filters.command, conf_symbol)],},
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    conv_handler24 = ConversationHandler(
        entry_points=[CommandHandler("updateproportion", update_proportion)],
        states={
            UPDATEPROP: [
                MessageHandler(Filters.text & ~Filters.command, updateProportionReal)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    dispatcher.add_handler(conv_handler)
    dispatcher.add_handler(conv_handler2)
    dispatcher.add_handler(conv_handler6)
    dispatcher.add_handler(conv_handler7)
    dispatcher.add_handler(conv_handler8)
    dispatcher.add_handler(conv_handler9)
    dispatcher.add_handler(conv_handler10)
    dispatcher.add_handler(conv_handler11)
    dispatcher.add_handler(conv_handler12)
    # dispatcher.add_handler(conv_handler13)
    dispatcher.add_handler(conv_handler14)
    # dispatcher.add_handler(conv_handler15)
    dispatcher.add_handler(conv_handler16)
    dispatcher.add_handler(conv_handler17)
    dispatcher.add_handler(conv_handler18)
    dispatcher.add_handler(conv_handler19)
    dispatcher.add_handler(conv_handler22)
    dispatcher.add_handler(conv_handler23)
    dispatcher.add_handler(conv_handler24)
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(CommandHandler("view", view_position))
    dispatcher.add_handler(CommandHandler("checkbal", check_balance))
    dispatcher.add_handler(CommandHandler("viewpnlstat", viewpnlstat))
    dispatcher.add_error_handler(error_callback)
    updater = updater2
    current_stream.resume()
    try:
        restore_save_data()
    except:
        logger.info("No data to restore.")
    reloading = False
    reload_announcement()
    updater.start_polling()
    is_reloading = False


def main():
    dispatcher = updater.dispatcher
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            AUTH: [MessageHandler(Filters.text & ~Filters.command, auth_check)],
            DISCLAIMER: [MessageHandler(Filters.regex("^(yes)$"), disclaimer_check)],
            PLATFORM: [
                MessageHandler(Filters.regex("^(1|2|3)$"), check_platform)
            ],  # DO COME BACK
            APIKEY: [MessageHandler(Filters.text & ~Filters.command, check_api)],
            APISECRET: [MessageHandler(Filters.text & ~Filters.command, check_secret)],
            CHECKPROP: [MessageHandler(Filters.text & ~Filters.command, check_ratio)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    conv_handler2 = ConversationHandler(
        entry_points=[CommandHandler("admin", admin)],
        states={
            AUTH2: [MessageHandler(Filters.text & ~Filters.command, auth_check2)],
            ANNOUNCE: [
                MessageHandler(Filters.text & ~Filters.command, announce),
                CommandHandler("save", save_to_file),
                CommandHandler("endall", end_everyone),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    conv_handler6 = ConversationHandler(
        entry_points=[CommandHandler("setallleverage", setAllLeverage)],
        states={
            REALSETLEV: [
                MessageHandler(Filters.text & ~Filters.command, setAllLeverageReal)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    conv_handler7 = ConversationHandler(
        entry_points=[CommandHandler("setleverage", set_leverage)],
        states={
            LEVTRADER: [
                MessageHandler(Filters.text & ~Filters.command, leverage_choosesymbol)
            ],
            REALSETLEV2: [
                MessageHandler(Filters.text & ~Filters.command, setLeverageReal)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    conv_handler8 = ConversationHandler(
        entry_points=[CommandHandler("setallproportion", set_all_proportion)],
        states={
            ALLPROP: [
                MessageHandler(Filters.text & ~Filters.command, setAllProportionReal)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    conv_handler9 = ConversationHandler(
        entry_points=[CommandHandler("setproportion", set_proportion)],
        states={
            PROPSYM: [
                MessageHandler(Filters.text & ~Filters.command, proportion_choosesymbol)
            ],
            REALSETPROP2: [
                MessageHandler(Filters.text & ~Filters.command, setProportionReal)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    conv_handler10 = ConversationHandler(
        entry_points=[CommandHandler("getleverage", get_leverage)],
        states={
            REALSETLEV3: [
                MessageHandler(Filters.text & ~Filters.command, getLeverageReal)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    conv_handler11 = ConversationHandler(
        entry_points=[CommandHandler("getproportion", get_proportion)],
        states={
            REALSETLEV4: [
                MessageHandler(Filters.text & ~Filters.command, getproportionReal)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    conv_handler12 = ConversationHandler(
        entry_points=[CommandHandler("end", end_all)],
        states={COCO: [MessageHandler(Filters.regex("^(yes)$"), realEndAll)],},
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    # conv_handler13 = ConversationHandler(
    #     entry_points=[CommandHandler('settmode',set_omode)],
    #     states={
    #         PROPSYM2:[MessageHandler(Filters.text & ~Filters.command,omode_choosesymbol)],
    #         REALSETPROP3:[MessageHandler(Filters.regex('^(0|1|2)$'),setomodeReal)],
    #     },
    #     fallbacks=[CommandHandler('cancel', cancel)],
    # )
    conv_handler14 = ConversationHandler(
        entry_points=[CommandHandler("setlmode", set_lmode)],
        states={REALSETLEV5: [MessageHandler(Filters.regex("^(0|1)$"), setlmodeReal)],},
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    # conv_handler15 = ConversationHandler(
    #     entry_points=[CommandHandler('setalltmode',set_allomode)],
    #     states={
    #         REALSETLEV6:[MessageHandler(Filters.regex('^(0|1|2)$'),setallomodeReal)],
    #     },
    #     fallbacks=[CommandHandler('cancel', cancel)],
    # )
    conv_handler16 = ConversationHandler(
        entry_points=[CommandHandler("changesr", change_safetyratio)],
        states={
            LEVTRADER6: [
                MessageHandler(Filters.text & ~Filters.command, confirm_changesafety)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    conv_handler17 = ConversationHandler(
        entry_points=[CommandHandler("setalltpsl", set_all_tpsl)],
        states={
            REALSETPROP4: [
                MessageHandler(Filters.text & ~Filters.command, setAllTpslReal)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    conv_handler18 = ConversationHandler(
        entry_points=[CommandHandler("settpsl", set_tpsl)],
        states={
            PROPSYM3: [
                MessageHandler(Filters.text & ~Filters.command, tpsl_choosesymbol)
            ],
            REALSETPROP5: [
                MessageHandler(Filters.text & ~Filters.command, setTpslReal)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    conv_handler19 = ConversationHandler(
        entry_points=[CommandHandler("gettpsl", get_tpsl)],
        states={
            REALSETLEV7: [MessageHandler(Filters.text & ~Filters.command, getTpslReal)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    conv_handler22 = ConversationHandler(
        entry_points=[CommandHandler("changeapi", choose_platform)],
        states={
            SEP3: [MessageHandler(Filters.regex("^(1|2|3)$"), change_api)],
            SEP1: [MessageHandler(Filters.text & ~Filters.command, change_secret)],
            SEP2: [MessageHandler(Filters.text & ~Filters.command, change_bnall)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    conv_handler23 = ConversationHandler(
        entry_points=[CommandHandler("closeposition", close_position)],
        states={CP1: [MessageHandler(Filters.text & ~Filters.command, conf_symbol)],},
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    conv_handler24 = ConversationHandler(
        entry_points=[CommandHandler("updateproportion", update_proportion)],
        states={
            UPDATEPROP: [
                MessageHandler(Filters.text & ~Filters.command, updateProportionReal)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
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
    # dispatcher.add_handler(conv_handler13)
    dispatcher.add_handler(conv_handler14)
    # dispatcher.add_handler(conv_handler15)
    dispatcher.add_handler(conv_handler16)
    dispatcher.add_handler(conv_handler17)
    dispatcher.add_handler(conv_handler18)
    dispatcher.add_handler(conv_handler19)
    dispatcher.add_handler(conv_handler22)
    dispatcher.add_handler(conv_handler23)
    dispatcher.add_handler(conv_handler24)
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(CommandHandler("view", view_position))
    dispatcher.add_handler(CommandHandler("checkbal", check_balance))
    dispatcher.add_handler(CommandHandler("viewpnlstat", viewpnlstat))
    dispatcher.add_error_handler(error_callback)
    current_stream = getStreamData()
    current_stream.start()
    try:
        restore_save_data()
    except:
        logger.info("No data to restore.")
    thr = threading.Thread(target=automatic_reload)
    thr.start()
    t2 = threading.Thread(target=save_trading_pnl)
    t2.start()
    reload_announcement()
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
