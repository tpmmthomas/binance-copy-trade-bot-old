from testbinance import CurrentUsers, UserLocks


class FetchLatestPosition(threading.Thread):
    def __init__(self,fetch_url,chat_id,name,uname,toTrade,tmode=None,lmode=None):
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
        if toTrade:
            self.proportion = {}
            self.leverage = {}
            self.tmode = tmode
            self.lmode = lmode
            UserLocks[self.chat_id].acquire()
            listSymbols = CurrentUsers[self.chat_id].bclient.get_symbols()
            UserLocks[self.chat_id].release()
            for symbol in listSymbols:
                self.proportion[symbol] = 0
                self.leverage[symbol] = 20

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
                    txtype.append("BuyLong")
                    txsymbol.append(row['symbol'])
                    txsize.append(size)
                    executePrice.append(row["Entry Price"])
                else:
                    txtype.append("BuyShort")
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
                    txtype.append("SellLong")
                    txsymbol.append(row['symbol'])
                    txsize.append(-size)
                    executePrice.append(row["Mark Price"])
                else:
                    txtype.append("SellShort")
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
                            txtype.append("BuyLong")
                            txsymbol.append(df2row[0])
                            txsize.append(changesize)
                            try:
                                exp = (newentry*newsize-oldentry*size)/changesize
                            except:
                                exp = 0
                            executePrice.append(exp)
                        else:
                            txtype.append("SellLong")
                            txsymbol.append(df2row[0])
                            txsize.append(changesize)
                            executePrice.append(newmark)
                        df2 = df2.drop(idx)
                        hasChanged = True
                        break
                    if not isPositive and newsize < 0:
                        changesize = newsize - size
                        if changesize > 0:
                            txtype.append("SellShort")
                            txsymbol.append(df2row[0])
                            txsize.append(changesize)
                            executePrice.append(newmark)
                        else:
                            txtype.append("BuyShort")
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
                        txtype.append("SellLong")
                        txsymbol.append(row['symbol'])
                        txsize.append(-size)
                        executePrice.append(oldmark)
                    else:
                        txtype.append("SellShort")
                        txsymbol.append(row['symbol'])
                        txsize.append(-size)
                        executePrice.append(oldmark)
            for index,row in df2.iterrows():
                size = row['size']  
                if isinstance(size,str):
                    size = size.replace(",","")
                size = float(size)
                if size >0:
                    txtype.append("BuyLong")
                    txsymbol.append(row['symbol'])
                    txsize.append(size)
                    executePrice.append(row['Entry Price'])
                else:
                    txtype.append("BuyShort")
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
                        UserLocks[self.chat_id].acquire()
                        CurrentUsers[self.chat_id].bclient.open_trade(txlist,self.proportion,self.leverage,self.lmode,self.tmode)
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
                    self.changes(self.prev_df,output["data"])
                    UserLocks[self.chat_id].acquire()
                    CurrentUsers[self.chat_id].bclient.open_trade(txlist,self.proportion,self.leverage,self.lmode,self.tmode)
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
        for symbol in allsymbols:
            if symbol in self.proportion:
                secondProportion[symbol] = self.proportion[symbol]
                secondLeverage[symbol] = self.leverage[symbol]
            else:
                secondProportion[symbol] = 0
                secondLeverage[symbol] = 20
        self.proportion = secondProportion
        self.leverage = secondLeverage

    def change_proportion(self,symbol,prop):
        if symbol not in self.proportion:
            updater.bot.sendMessage(chat_id=self.chat_id,text="Sorry,but this symbol is not available right now.")
        self.proportion[symbol] = prop
        logger.info(f"{self.uname} Successfully changed proportion.")
        return

    def get_proportion(self,symbol):
        if symbol not in self.proportion:
            updater.bot.sendMessage(chat_id=self.chat_id,text="Sorry,but this symbol is not available right now.")
            return
        updater.bot.sendMessage(chat_id=self.chat_id,text=f"The proportion for {symbol} is {self.proportion[symbol]}x.")
        logger.info(f"{self.uname} Successfully queried proportion.")
        return
    
    def change_all_proportion(self,prop):
        for symbol in self.proportion:
            self.proportion[symbol] = prop
        logger.info(f"{self.uname} Successfully changed all proportion.")
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
        return

    def get_leverage(self,symbol):
        if symbol not in self.leverage:
            updater.bot.sendMessage(chat_id=self.chat_id,text="Sorry,but this symbol is not available right now.")
            return
        updater.bot.sendMessage(chat_id=self.chat_id,text=f"The leverage for {symbol} is {self.leverage[symbol]}x.")
        logger.info(f"{self.uname} Successfully queried leverage.")
        return
    
    def change_all_proportion(self,lev):
        try:
            lev = int(lev)
            assert lev>=1 and lev<=125
        except:
            updater.bot.sendMessage(chat_id=self.chat_id,text="Sorry,but the leverage must be an integer between 1 and 125.")
            return
        for symbol in self.leverage:
            self.leverage[symbol] = lev
        logger.info(f"{self.uname} Successfully changed all leverage.")
        return