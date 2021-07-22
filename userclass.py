from bs4.builder import TreeBuilderRegistry


class BinanceClient:
    def __init__(self,chat_id,uname,api_key,api_secret):
        self.client = Client(api_key,api_secret)
        self.chat_id = chat_id
        self.uname = uname
        self.precision = {}
        info = self.client.futures_exchange_info()
        try:
            self.client.futures_change_position_mode(dualSidePosition=True)
        except BinanceAPIException as e:
            logger.error(e)
        for thing in info['symbols']:
            self.precision[thing['symbol']] = thing['quantityPrecision']
        try:
            for symbol in self.precision:
                self.client.futures_change_margin_type(symbol=symbol,marginType="CROSSED")
        except BinanceAPIException as e:
            logger.error(e)

    def get_symbols(self):
        self.reload()
        symbolList = []
        for symbol in self.precision:
            symbolList.append(symbol)
        return symbolList

    def open_trade(self,df,proportion,leverage,lmode,tmode):
        #TODO: consider user positions as well.
        df = df.values
        for tradeinfo in df:
            types = tradeinfo[0].upper()
            if types[:3] == "BUY":
                side = types[:3]
                positionSide = types[3:]
                if lmode != 2:
                    try:
                        self.client.futures_change_leverage(symbol=tradeinfo[1],leverage=leverage[tradeinfo[1]])
                    except:
                        pass
            else:
                side = types[:4]
                positionSide = types[4:]
            quant = tradeinfo[2] * proportion[tradeinfo[1]]
            if quant == 0:
                continue
            reqPrecision = self.precision[tradeinfo[1]]
            quant =  "{:0.0{}f}".format(quant,reqPrecision)
            target_price = "{:0.0{}f}".format(float(tradeinfo[3],reqPrecision))
            #TODO: adjust target price by getting current price info
            if tmode == 0:
                try:
                    tosend = f"Trying to execute the following trade:\nSymbol: {tradeinfo[1]}\nSide: {side}\npositionSide: {positionSide}\ntype: MARKET\nquantity: {quant}"
                    updater.bot.sendMessage(chat_id=self.chat_id,text=tosend)
                    self.client.futures_create_order(symbol=tradeinfo[1],side=side,positionSide=positionSide,type="MARKET",quantity=quant)
                    logger.info(f"{self.uname} opened order.")
                    
                except BinanceAPIException as e:
                    logger.error(e)
            else:
                try:
                    tosend = f"Trying to execute the following trade:\nSymbol: {tradeinfo[1]}\nSide: {side}\npositionSide: {positionSide}\ntype: LIMIT\nquantity: {quant}\nPrice: {target_price}"
                    updater.bot.sendMessage(chat_id=self.chat_id,text=tosend)
                    self.client.futures_create_order(symbol=tradeinfo[1],side=side,positionSide=positionSide,type="LIMIT",quantity=quant,price=target_price,timeInForce="GTC")
                    logger.info(f"{self.uname} opened order.")
                except BinanceAPIException as e:
                    logger.error(e)
        return

    def reload(self):
        info = self.client.futures_exchange_info()
        secondPrecision = {}
        for thing in info['symbols']:
            secondPrecision[thing['symbol']] = thing['quantityPrecision']
        self.precision = secondPrecision          

class users:
    def __init__(self,chat_id,uname,init_trader,trader_name,toTrade,tmode=None,lmode=None,api_key=None,api_secret=None):
        self.chat_id = chat_id
        self.toTrade = toTrade
        self.trader_urls = [init_trader]
        self.trader_names = [trader_name] 
        self.threads = []
        self.is_handling = False
        self.username = uname
        if toTrade:
            self.bclient = BinanceClient(chat_id,uname,api_key,api_secret)
            self.opened_positions = []
            thr = FetchLatestPosition(init_trader,chat_id,trader_name,uname,toTrade,tmode,lmode) 
        else:
            thr = FetchLatestPosition(init_trader,chat_id,trader_name,uname,toTrade)
        thr.start()
        self.threads.append(thr)

    def add_trader(self,url,name,tmode=None,lmode=None):
        self.trader_urls.append(url)
        self.trader_names.append(name)
        if self.toTrade:
            thr = FetchLatestPosition(url,self.chat_id,name,self.toTrade,tmode,lmode)
        else:
            thr = FetchLatestPosition(url,self.chat_id,name,self.toTrade)
        thr.start()
        self.threads.append(thr)

    def delete_trader(self,idx):
        self.trader_urls.pop(idx)
        self.trader_names.pop(idx)
        self.threads[idx].stop()
        self.threads.pop(idx)
