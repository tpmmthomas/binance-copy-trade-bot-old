import hmac, hashlib, time, requests, math, threading


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
                self.stepsize[thing["symbol"]] = float(thing["minQuantity"])

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
        if response["message"] == "Success":
            updater.bot.sendMessage(chat_id=self.chat_id, text="Success!")
            for trader in CurrentUsers[self.chat_id].threads:
                trader.positions[symbol + "LONG"] = 0
                trader.positions[symbol + "SHORT"] = 0
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
                response = response["list"][0]
                if response["orderStatus"] == 3:
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
                            ] += float(response["cumQty"])
                        else:
                            CurrentUsers[self.chat_id].threads[idx].positions[
                                positionKey
                            ] = float(response["cumQty"])
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
                            ] -= float(response["cumQty"])
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
                    logger.info(
                        f"DEBUG {self.uname} {positionKey}: {CurrentUsers[self.chat_id].threads[idx].positions[positionKey]}"
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
                            ] -= float(response["cumQty"])
                        else:
                            CurrentUsers[self.chat_id].threads[idx].positions[
                                positionKey
                            ] = 0
                        UserLocks[self.chat_id].release()
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
    ):
        try:
            self.reload()
        except:
            time.sleep(10)
        logger.info("DEBUG\n" + df.to_string())
        df = df.values
        for tradeinfo in df:
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
            elif not isOpen and quant / positions[checkKey] > 0.9:
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
                    secondstepsize[thing["symbol"]] = float(thing["minQuantity"])
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

    def round_up(self, quant, minsize):
        return math.ceil(quant / minsize)

