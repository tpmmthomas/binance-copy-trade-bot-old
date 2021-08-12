import time, requests, math, threading
import bybit


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
            )
            self.client.LinearPositions.LinearPositions_switchMode(
                symbol=symbol, tp_sl_mode="Partial"
            )

    def get_symbols(self):
        symbolList = []
        for symbol in self.stepsize:
            symbolList.append(symbol)
        return symbolList

    def close_position(self, symbol):
        result = self.client.LinearPositions.LinearPositions_myPosition(
            symbol=symbol
        ).result()
        response = ""
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
        for trader in CurrentUsers[self.chat_id].threads:
            trader.positions[symbol + "LONG"] = 0
            trader.positions[symbol + "SHORT"] = 0
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
                    ).result()
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
                    ).result()
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
                    ).result()
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
                    ).result()
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
                ).result()
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
                        idx = CurrentUsers[self.chat_id].trader_names.index(uname)
                        UserLocks[self.chat_id].acquire()  # needed bc run as thread
                        if (
                            positionKey
                            in CurrentUsers[self.chat_id].threads[idx].positions
                        ):
                            CurrentUsers[self.chat_id].threads[idx].positions[
                                positionKey
                            ] += float(result["cum_exec_qty"])
                        else:
                            CurrentUsers[self.chat_id].threads[idx].positions[
                                positionKey
                            ] = float(result["cum_exec_qty"])
                        UserLocks[self.chat_id].release()
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
                        idx = CurrentUsers[self.chat_id].trader_names.index(uname)
                        UserLocks[self.chat_id].acquire()  # needed bc run as thread
                        if (
                            positionKey
                            in CurrentUsers[self.chat_id].threads[idx].positions
                        ):
                            CurrentUsers[self.chat_id].threads[idx].positions[
                                positionKey
                            ] -= float(result["cum_exec_qty"])
                        else:
                            CurrentUsers[self.chat_id].threads[idx].positions[
                                positionKey
                            ] = 0
                        if (
                            CurrentUsers[self.chat_id]
                            .threads[idx]
                            .positions[positionKey]
                            < 0
                        ):
                            CurrentUsers[self.chat_id].threads[idx].positions[
                                positionKey
                            ] = 0
                        UserLocks[self.chat_id].release()
                        # check positions thenn close all
                        res = self.client.LinearPositions.LinearPositions_myPosition(
                            symbol=symbol
                        ).result()["result"]
                        for pos in res:
                            logger.info(str(pos))
                            if (
                                pos["side"] == result["side"]
                                and float(pos["size"]) == 0
                            ):
                                CurrentUsers[self.chat_id].threads[idx].positions[
                                    positionKey
                                ] = 0
                    logger.info(
                        f"DEBUG {self.uname} {positionKey}: {CurrentUsers[self.chat_id].threads[idx].positions[positionKey]}"
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
                        idx = CurrentUsers[self.chat_id].trader_names.index(uname)
                        UserLocks[self.chat_id].acquire()  # needed bc run as thread
                        if (
                            positionKey
                            in CurrentUsers[self.chat_id].threads[idx].positions
                        ):
                            CurrentUsers[self.chat_id].threads[idx].positions[
                                positionKey
                            ] += updatedQty
                        else:
                            CurrentUsers[self.chat_id].threads[idx].positions[
                                positionKey
                            ] = updatedQty
                        UserLocks[self.chat_id].release()
                    else:
                        idx = CurrentUsers[self.chat_id].trader_names.index(uname)
                        UserLocks[self.chat_id].acquire()  # needed bc run as thread
                        if (
                            positionKey
                            in CurrentUsers[self.chat_id].threads[idx].positions
                        ):
                            CurrentUsers[self.chat_id].threads[idx].positions[
                                positionKey
                            ] -= float(result["cum_exec_qty"])
                        else:
                            CurrentUsers[self.chat_id].threads[idx].positions[
                                positionKey
                            ] = 0
                        UserLocks[self.chat_id].release()
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
                )
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
    ):

        try:
            self.reload()
        except:
            time.sleep(10)
        logger.info("DEBUG\n" + df.to_string())
        df = df.values
        for tradeinfo in df:
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
                        self.client.Positions.Positions_saveLeverage(
                            symbol=tradeinfo[1],
                            leverage=leverage[tradeinfo[1]],
                            leverage_only=True,
                        )
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
            elif not isOpen and quant / positions[checkKey] > 0.9:
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
                ]["mark_price"]
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
                    response = self.client.LinearOrder.LinearOrder_new(
                        side=side,
                        symbol=tradeinfo[1],
                        order_type="Market",
                        qty=quant,
                        time_in_force="GoodTillCancel",
                        reduce_only=False,
                        close_on_trigger=False,
                    ).result()
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
                    response = self.client.LinearOrder.LinearOrder_new(
                        side=side,
                        symbol=tradeinfo[1],
                        order_type="Limit",
                        qty=quant,
                        price=target_price,
                        time_in_force="GoodTillCancel",
                        reduce_only=False,
                        close_on_trigger=False,
                    ).result()
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

    def change_keys(self, apikey, apisecret):
        self.auth = Auth(apikey, apisecret)

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

    def round_up(n, decimals=0):
        multiplier = 10 ** decimals
        return math.ceil(n * multiplier) / multiplier

