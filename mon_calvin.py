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
from unicorn_binance_websocket_api.unicorn_binance_websocket_api_manager import (
    BinanceWebSocketApiManager,
)
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
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
(
    AUTH,
    SEP1,
    SEP2,
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
) = range(51)

logger = logging.getLogger(__name__)
updater = Updater(cnt.bot_token2)

current_users = {}
current_stream = None
lastPositions = "Welcome!"
longOrShort = {}
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
        self.socket = BinanceWebSocketApiManager(exchange="binance.com-futures")
        self.socket.create_stream(
            ["arr"], ["!userData"], api_key=cnt.api_key, api_secret=cnt.api_secret
        )
        self.isStop = threading.Event()
        self.client = Client(cnt.api_key, cnt.api_secret)

    def run(self):
        time.sleep(2)
        while not self.isStop.is_set():
            if self.socket.is_manager_stopping():
                exit(0)
            buffer = self.socket.pop_stream_data_from_stream_buffer()
            if buffer is False:
                time.sleep(2)
            else:
                buffer = json.loads(buffer)
                if buffer["e"] == "ORDER_TRADE_UPDATE":
                    logger.info(f"DEBUG: {buffer['o']['X']}")
                    # if buffer["o"]["X"] == "NEW":
                    #     while q.full():
                    #         time.sleep(1)
                    #     q.put((buffer, 0))
                    # elif buffer["o"]["X"] == "CANCELED":
                    #     while q.full():
                    #         time.sleep(1)
                    #     q.put((buffer, 1))
                    if buffer["o"]["X"] == "FILLED":
                        q.put(buffer)
                logger.info(str(buffer))

    def stop(self):
        self.isStop.set()


def reset_positions():
    time.sleep(3)
    global stop_update
    stop_update = False


def get_positions():
    global lastPositions
    global stop_update
    if not stop_update:
        try:
            result = current_stream.client.futures_position_information()
        except:
            logger.error("Cannot retrieve latest position.")
            return
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
                pside = "LONG" if float(tsize) >= 0 else "SHORT"
                EnPrice.append(pos["entryPrice"])
                MarkPrice.append(pos["markPrice"])
                PNL.append(pos["unRealizedProfit"])
                margin.append(pos["leverage"])
                longOrShort[pos["symbol"]] = pside
                listTradingSymbols.append(pos["symbol"])
                for user in current_users:
                    if current_users[user].lmode == 0:
                        current_users[user].leverage[pos["symbol"]] = int(
                            pos["leverage"]
                        )
        todel = []
        for symbols in longOrShort:
            if not symbols in listTradingSymbols:
                todel.append(symbols)
        for symbol in todel:
            del longOrShort[symbol]
        if len(symbol) > 0 and len(size) > 0:
            lastPositions = pd.DataFrame(
                {
                    "symbol": symbol,
                    "size": size,
                    "Entry Price": EnPrice,
                    "Mark Price": MarkPrice,
                    "PNL": PNL,
                    "leverage": margin,
                }
            ).to_string()
        else:
            lastPositions = "No Positions."
        stop_update = True
        t = threading.Thread(target=reset_positions)
        t.start()


def get_newest_trade():
    global current_stream
    global stop_update
    time.sleep(10)
    while True:
        while q.empty():
            time.sleep(1)
        stop_update = True
        logger.info("Received new update.")
        result = q.get()
        result = result["o"]
        symbol = result["s"]
        side = result["S"]
        qty = result["q"]
        ptype = result["o"]
        if side == "BUY" and not symbol in longOrShort:
            ptype = "OpenLong"
        elif side == "SELL" and not symbol in longOrShort:
            ptype = "OpenShort"
        elif side == "BUY":
            ptype = "OpenLong" if longOrShort[symbol] == "LONG" else "CloseShort"
        else:
            ptype = "OpenShort" if longOrShort[symbol] == "SHORT" else "CloseLong"
        price = result["p"]
        ttype = result["o"]
        for chat_id in current_users:
            updater.bot.sendMessage(
                chat_id=chat_id,
                text=f"The following trade is opened in Kevin's account:\nSymbol: {symbol}\nType: {ptype}\nExcPrice: {price}\nQuantity: {qty}\nOrder Type: {ttype}",
            )
            if ttype in ["MARKET", "LIMIT"]:
                current_users[chat_id].open_trade(result, ptype)
        stop_update = False
        t1 = threading.Thread(target=show_positions)
        t1.start()
        # else:
        #     result = result[0]["o"]
        #     cid = result["c"]
        #     symbol = result["s"]
        #     for chat_id in current_users:
        #         current_users[chat_id].cancel_trade(cid, symbol)
        #         updater.bot.sendMessage(
        #             chat_id=chat_id, text="The trade was cancelled in Kevin's account."
        #         )


def automatic_reload():
    global current_stream
    while True:
        time.sleep(23 * 60 * 60)
        current_stream.stop()
        time.sleep(1)
        newStream = getStreamData()
        newStream.start()
        current_stream = newStream
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
    update.message.reply_text("Please provide your API Key from Binance.")
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
        ratio = ratio / 38500
        ratio = round(ratio, 5)
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
            }
        )
    with open("userdata_calvin.pickle", "wb") as f:
        pickle.dump(save_items, f)
    logger.info("Saved user current state.")
    return ConversationHandler.END


def view_position(update: Update, context: CallbackContext):
    get_positions()
    if isinstance(lastPositions, str):
        updater.bot.sendMessage(chat_id=update.message.chat_id, text=lastPositions)
    else:
        updater.bot.sendMessage(
            chat_id=update.message.chat_id, text=lastPositions.to_string()
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


def change_api(update: Update, context: CallbackContext):
    if not update.message.chat_id in current_users:
        update.message.reply_text("Please initalize with /start first.")
        return ConversationHandler.END
    update.message.reply_text("Please provide your API Key from Binance.")
    update.message.reply_text(
        "*SECURITY WARNING*\nTo ensure safety of funds, please note the following before providing your API key:\n1. Set up a new key for this program, don't reuse your other API keys.\n2. Restrict access to this IP: *35.229.163.161*\n3. Only allow these API Restrictions: 'Enable Reading' and 'Enable Futures'.",
        parse_mode=telegram.ParseMode.MARKDOWN,
    )
    return SEP1


def change_secret(update: Update, context: CallbackContext):
    user = current_users[update.message.chat_id]
    logger.info(f"User {user.uname} changing api keys.")
    update.message.reply_text(
        "Please provide your Secret Key.\n*DELETE YOUR MESSAGE IMMEDIATELY AFTERWARDS.*",
        parse_mode=telegram.ParseMode.MARKDOWN,
    )
    context.user_data["api_key"] = update.message.text
    return SEP2


def change_bnall(update: Update, context: CallbackContext):
    user = current_users[update.message.chat_id]
    user.api_key = context.user_data["api_key"]
    user.api_secret = update.message.text
    user.client = Client(user.api_key, user.api_secret)
    update.message.reply_text("Success!")
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
    ):
        self.chat_id = chat_id
        self.uname = uname
        self.name = "CalvinTsai"
        self.api_key = api_key
        self.api_secret = api_secret
        self.client = Client(api_key, api_secret)
        self.stepsize = {}
        self.ticksize = {}
        self.tpslids = {}
        # self.unfulfilledPos = {}  # Map Kevin's Client ID to own orderId
        self.safety_ratio = safety_ratio
        info = self.client.futures_exchange_info()
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
                    if skey in self.tpslids:
                        self.tpslids[skey].append(result["orderId"])
                    else:
                        self.tpslids[skey] = []
                        self.tpslids[skey].append(result["orderId"])
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
                    if skey in self.tpslids:
                        self.tpslids[skey].append(result["orderId"])
                    else:
                        self.tpslids[skey] = []
                        self.tpslids[skey].append(result["orderId"])
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
                    if skey in self.tpslids:
                        self.tpslids[skey].append(result["orderId"])
                    else:
                        self.tpslids[skey] = []
                        self.tpslids[skey].append(result["orderId"])
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
                    if skey in self.tpslids:
                        self.tpslids[skey].append(result["orderId"])
                    else:
                        self.tpslids[skey] = []
                        self.tpslids[skey].append(result["orderId"])
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
                    # if cid in self.unfulfilledPos:
                    #     del self.unfulfilledPos[cid]
                    # ADD TO POSITION
                    if isOpen:
                        if positionKey in self.positions:
                            self.positions[positionKey] += float(result["executedQty"])
                        else:
                            self.positions[positionKey] = float(result["executedQty"])
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
                            return
                    else:
                        if positionKey in self.positions:
                            self.positions[positionKey] -= float(result["executedQty"])
                        else:
                            self.positions[positionKey] = 0
                        try:
                            res = self.client.futures_position_information(
                                symbol=symbol
                            )
                        except BinanceAPIException as e:
                            logger.error(str(e))
                            return
                        for pos in res:
                            if (
                                pos["positionSide"] == result["positionSide"]
                                and float(pos["positionAmt"]) == 0
                            ):
                                if positionKey in self.tpslids:
                                    idlist = self.tpslids[positionKey]
                                    try:
                                        for id in idlist:
                                            self.client.futures_cancel_order(
                                                symbol=symbol, orderId=id
                                            )
                                        self.tpslids[positionKey] = []
                                    except BinanceAPIException as e:
                                        logger.error(str(e))
                                self.positions[positionKey] = 0

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
                    # if cid in self.unfulfilledPos:
                    #     del self.unfulfilledPos[cid]
                    return
                elif result["status"] == "PARTIALLY_FILLED":
                    updatedQty = float(result["executedQty"]) - executed_qty
                    if isOpen:
                        if positionKey in self.positions:
                            self.positions[positionKey] += updatedQty
                        else:
                            self.positions[positionKey] = updatedQty
                    else:
                        if positionKey in self.positions:
                            self.positions[positionKey] -= float(result["executedQty"])
                        else:
                            self.positions[positionKey] = 0
                    executed_qty = float(result["executedQty"])
            except:
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
        # if cid in self.unfulfilledPos:
        #     del self.unfulfilledPos[cid]

    def open_trade(self, tradeinfo, type):
        logger.info("Attempting to open trade.")
        logger.info(str(tradeinfo))
        self.reload()
        balance, collateral, coin = 0, 0, ""
        try:
            coin = "USDT"
            for asset in self.client.futures_account()["assets"]:
                if asset["asset"] == "USDT":
                    balance = asset["maxWithdrawAmount"]
                    break
            if tradeinfo["s"][-4:] == "BUSD":
                tradeinfo["s"] = tradeinfo["s"][:-4] + "USDT"
                updater.bot.sendMessage(
                    chat_id=self.chat_id,
                    text="Our system only supports USDT. This trade will be executed in USDT instead of BUSD.",
                )
                # mids.append(result.message_id)
        except BinanceAPIException as e:
            coin = "USDT"
            balance = "0"
            logger.error(e)
        balance = float(balance)
        # mids = []
        isOpen = False
        type = type.upper()
        ps = ""
        if type[:4] == "OPEN":
            isOpen = True
            ps = type[4:]
        else:
            ps = type[5:]
        try:
            self.client.futures_change_leverage(
                symbol=tradeinfo["s"], leverage=self.leverage[tradeinfo["s"]]
            )
        except:
            pass
        quant = abs(float(tradeinfo["q"])) * self.proportion[tradeinfo["s"]]
        checkKey = tradeinfo["s"].upper() + ps
        if not isOpen and (
            (checkKey not in self.positions) or (self.positions[checkKey] < quant)
        ):
            if checkKey not in self.positions or self.positions[checkKey] == 0:
                updater.bot.sendMessage(
                    chat_id=self.chat_id,
                    text=f"Close {checkKey}: This trade will not be executed because your opened positions with this trader is 0.",
                )
                return
            elif self.positions[checkKey] < quant:
                quant = min(self.positions[checkKey], quant)
                updater.bot.sendMessage(
                    chat_id=self.chat_id,
                    text=f"Close {checkKey}: The trade quantity will be less than expected, because you don't have enough positions to close.",
                )
                # mids.append(result.message_id)
        elif not isOpen and quant / self.positions[checkKey] > 0.9:
            quant = max(self.positions[checkKey], quant)
        if quant == 0:
            updater.bot.sendMessage(
                chat_id=self.chat_id,
                text=f"{tradeinfo['S']} {checkKey}: This trade will not be executed because size = 0. Adjust proportion if you want to follow.",
            )
            return

        latest_price = float(
            self.client.futures_mark_price(symbol=tradeinfo["s"])["markPrice"]
        )
        reqticksize = self.ticksize[tradeinfo["s"]]
        reqstepsize = self.stepsize[tradeinfo["s"]]
        quant = round_up(quant, reqstepsize)
        collateral = (latest_price * quant) / self.leverage[tradeinfo["s"]]
        quant = str(quant)
        if isOpen:
            updater.bot.sendMessage(
                chat_id=self.chat_id,
                text=f"For the following trade, you will need {collateral:.3f}{coin} as collateral.",
            )
            # mids.append(result.message_id)
            if collateral >= balance * self.safety_ratio:
                updater.bot.sendMessage(
                    chat_id=self.chat_id,
                    text=f"WARNING: this trade will take up more than {self.safety_ratio*100}% of your available balance. It will NOT be executed. Manage your risks accordingly and reduce proportion if necessary.",
                )
                return
        target_price = "{:0.0{}f}".format(float(tradeinfo["p"]), reqticksize)
        # if tradeinfo["o"] == "MARKET":
        try:
            tosend = f"Executing the following trade:\nSymbol: {tradeinfo['s']}\nSide: {tradeinfo['S']}\npositionSide: {ps}\ntype: MARKET\nquantity: {quant}"
            updater.bot.sendMessage(chat_id=self.chat_id, text=tosend)
            # mids.append(result.message_id)
            rvalue = self.client.futures_create_order(
                symbol=tradeinfo["s"],
                side=tradeinfo["S"],
                positionSide=ps,
                type="MARKET",
                quantity=quant,
            )
            logger.info(f"{self.uname} opened order.")
            # self.unfulfilledPos[cid] = (rvalue["orderId"], mids)
            positionKey = tradeinfo["s"] + ps
            t1 = threading.Thread(
                target=self.query_trade,
                args=(
                    rvalue["orderId"],
                    tradeinfo["s"],
                    positionKey,
                    isOpen,
                    self.uname,
                    self.take_profit_percent[tradeinfo["s"]],
                    self.stop_loss_percent[tradeinfo["s"]],
                    self.leverage[tradeinfo["s"]],
                ),
            )
            t1.start()
        except BinanceAPIException as e:
            logger.error(e)
            if not isOpen and str(e).find("2022") >= 0:
                positionKey = tradeinfo["s"] + ps
                self.positions[positionKey] = 0
            updater.bot.sendMessage(chat_id=self.chat_id, text=str(e))
        # elif tradeinfo["o"] == "LIMIT":
        #     try:
        #         target_price = float(target_price)
        #         if ps == "LONG":
        #             target_price = min(latest_price, target_price)
        #         else:
        #             target_price = max(latest_price, target_price)
        #     except:
        #         pass
        #     target_price = "{:0.0{}f}".format(float(target_price), reqticksize)
        #     try:
        #         tosend = f"Executing the following trade:\nSymbol: {tradeinfo['s']}\nSide: {tradeinfo['S']}\npositionSide: {ps}\ntype: LIMIT\nquantity: {quant}\nPrice: {target_price}"
        #         result = updater.bot.sendMessage(chat_id=self.chat_id, text=tosend)
        #         # mids.append(result.message_id)
        #         rvalue = self.client.futures_create_order(
        #             symbol=tradeinfo["s"],
        #             side=tradeinfo["S"],
        #             positionSide=ps,
        #             type="LIMIT",
        #             quantity=quant,
        #             price=target_price,
        #             timeInForce="GTC",
        #         )
        #         logger.info(f"{self.uname} opened order.")
        #         # self.unfulfilledPos[cid] = (rvalue["orderId"], mids)
        #         positionKey = tradeinfo["s"] + ps
        #         t1 = threading.Thread(
        #             target=self.query_trade,
        #             args=(
        #                 rvalue["orderId"],
        #                 tradeinfo["s"],
        #                 positionKey,
        #                 isOpen,
        #                 self.uname,
        #                 self.take_profit_percent[tradeinfo["s"]],
        #                 self.stop_loss_percent[tradeinfo["s"]],
        #                 self.leverage[tradeinfo["s"]],
        #                 tosend,
        #                 cid,
        #             ),
        #         )
        #         t1.start()
        #     except BinanceAPIException as e:
        #         logger.error(e)
        #         updater.bot.sendMessage(chat_id=self.chat_id, text=str(e))

    # def cancel_trade(self, cid, symbol):
    #     logger.info("Trying to cancel trade")
    #     if cid in self.unfulfilledPos:
    #         logger.info(f"{self.uname} canceled order.")
    #         for mid in self.unfulfilledPos[cid][1]:
    #             updater.bot.delete_message(chat_id=self.chat_id, message_id=mid)
    #         try:
    #             self.client.futures_cancel_order(
    #                 symbol=symbol, orderId=self.unfulfilledPos[cid][0]
    #             )
    #         except BinanceAPIException as e:
    #             logger.error(str(e))
    #             updater.bot.send_message(chat_id=self.chat_id, text=str(e))
    #         del self.unfulfilledPos[cid]

    def reload(self):
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

    def change_safety_ratio(self, safety_ratio):
        logger.info(f"{self.uname} changed safety ratio.")
        self.safety_ratio = safety_ratio
        updater.bot.sendMessage(
            chat_id=self.chat_id, text="Succesfully changed safety ratio."
        )
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
        )


def main():
    dispatcher = updater.dispatcher
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            AUTH: [MessageHandler(Filters.text & ~Filters.command, auth_check)],
            DISCLAIMER: [MessageHandler(Filters.regex("^(yes)$"), disclaimer_check)],
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
        entry_points=[CommandHandler("changeapi", change_api)],
        states={
            SEP1: [MessageHandler(Filters.text & ~Filters.command, change_secret)],
            SEP2: [MessageHandler(Filters.text & ~Filters.command, change_bnall)],
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
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(CommandHandler("view", view_position))
    current_stream = getStreamData()
    current_stream.start()
    try:
        restore_save_data()
    except:
        logger.info("No data to restore.")
    thr = threading.Thread(target=automatic_reload)
    thr.start()
    thr2 = threading.Thread(target=get_newest_trade)
    thr2.start()
    thr3 = threading.Thread(target=get_positions)
    thr3.start()

    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
