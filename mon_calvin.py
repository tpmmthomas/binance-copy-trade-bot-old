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
import queue
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
from ast import literal_eval
q = queue.Queue(200)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

logger = logging.getLogger(__name__)

updater = Updater(cnt.bot_token2)

current_users = []
current_stream = None

class getStreamData(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.socket = BinanceWebSocketApiManager(exchange="binance.com-futures")
        self.socket.create_stream(["arr"],["!userData"],api_key=cnt.api_key,api_secret=cnt.api_secret)
        self.isStop = threading.Event()

    def run(self):
        time.sleep(2)
        while not self.isStop.is_set():
            if self.socket.is_manager_stopping():
                exit(0)
            buffer = self.socket.pop_stream_data_from_stream_buffer()
            if buffer is False:
                time.sleep(5)
            else:
                buffer = literal_eval(buffer)
                if buffer["e"] == "ORDER_TRADE_UPDATE":
                    if  buffer["o"]["X"] == "FILLED":
                        while q.full():
                            time.sleep(1)
                        q.put(buffer)
                logger.info(str(buffer))

    def stop(self):
        self.isStop.set()

def get_newest_trade():
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
        for chat_id in current_users:
            updater.bot.sendMessage(chat_id=chat_id,text=f"The following trade is executed:\nSymbol: {symbol}\nType: {type}\nside: {side}\nExcPrice: {price}\nQuantity: {qty}")

def automatic_reload():
    while True:
        time.sleep(23*60*60)
        current_stream.stop()
        newStream = getStreamData()
        newStream.start()
        current_stream = newStream

def start(update: Update, context: CallbackContext):
    if update.message.chat_id in current_users:
        update.message.reply_text("You have already initialized. No need to do it again.")
    update.message.reply_text("Thanks! you have been initialized.")
    current_users.append(update.message.chat_id)

def end(update: Update, context: CallbackContext):
    if not update.message.chat_id in current_users:
        update.message.reply_text("You have already initialized. No need to do it again.")
    update.message.reply_text("Bye!")
    current_users.remove(update.message.chat_id)

def main():
    dispatcher = updater.dispatcher
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("end", end))
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