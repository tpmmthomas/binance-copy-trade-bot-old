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
            if pos['positionAmt'] != 0:
                symbol.append(pos['symbol'])
                tsize = pos['positionAmt'] if pos['positionSide'] == "LONG" else "-"+pos['positionAmt']
                size.append(tsize)
                EnPrice.append(pos['entryPrice'])
                MarkPrice.append(pos['markPrice'])
                PNL.append(pos['unRealizedProfit'])
                margin.append(pos['leverage'])
        if len(symbol) > 0:
            return pd.DataFrame({'symbol':symbol,'size':size,"Entry Price":EnPrice,"Mark Price":MarkPrice,"PNL":PNL,"leverage":margin}).to_string()
        return "No Positions."

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
            current_users[chat_id].open_trade(result)

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
        return
    update.message.reply_text("Thanks! you have been initialized.")
    current_users.append(update.message.chat_id)

def end(update: Update, context: CallbackContext):
    if not update.message.chat_id in current_users:
        update.message.reply_text("You have already initialized. No need to do it again.")
        return
    update.message.reply_text("Bye!")
    current_users.remove(update.message.chat_id)


class userClient:
    def __init__(self,chat_id,uname,safety_ratio,api_key,api_secret,tp=None,sl=None,tmode=None,lmode=None,positions=None,proportion=None,Leverage=None):
        self.chat_id = chat_id
        self.uname = uname
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
            updater.bot.sendMessage(chat_id=self.chat_id,text=f"{side} {checkKey}: This trade will not be executed because size = 0. Adjust proportion if you want to follow.")
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