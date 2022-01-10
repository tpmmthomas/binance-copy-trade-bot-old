# binance-copy-trade-bot (still in development)
This program uses web scraping to monitor the positions opened by traders sharing their positions on Binance Futures Leaderboard. We then mimic the trade in your account using the Binance api.
### Environment setup (Recommended)

#### Using Conda
At your target directory, execute the following:   
```
conda create -n trading python=3.9 -y
conda activate trading
git clone https://github.com/tpmmthomas/binance-copy-trade-bot.git
cd binance-copy-trade-bot
pip install -r requirements.txt
```
### Software setup 
1. Download chrome browser at https://www.google.com/intl/zh-CN/chrome/
2. Download chrome driver at https://chromedriver.chromium.org/downloads
3. Setup a telegram bot using `Botfather` (details on telegram official site) and mark the access token.
4. `mv constants_sample.py constants.py` and fill in the required fields
5. Fill in the required fields at `config/config.py`
6. Run `mon_position.py` (Suggest to set it up as a service with systemctl, lots of tutorials available online.)

### Disclaimer

This software is for non-commercial purposes only. Do not risk money which you are afraid to lose.  

USE THIS SOFTWARE AT YOUR OWN RISK. THE AUTHORS ASSUME NO RESPONSIBILITY FOR YOUR TRADING RESULTS.     

Start by running backtesting of the bot first. Do not engage money before you understand how it works and what profit/loss you should expect.  


