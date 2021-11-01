import pymongo

myclient = pymongo.MongoClient("mongodb://localhost:27018/")

mydb = myclient["mydatabase"]

mycol = mydb["customers"]
mydict = {"name": "John", "address": "Highway 37"}

x = mycol.insert_one(mydict)
