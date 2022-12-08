import json
import boto3
from boto3.dynamodb.conditions import Key, Attr
import time
import requests

AWS_ACCESS_KEY=""
AWS_SECRET_ACCESS_KEY=""
AWS_REGION="us-east-1"
DYNAMODB_USER_TABLE='StormTrooperUsers'
EMAIL=''
ses = boto3.client('ses', aws_access_key_id=AWS_ACCESS_KEY,
                            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                            region_name=AWS_REGION)
                            
dynamodb = boto3.resource('dynamodb', aws_access_key_id=AWS_ACCESS_KEY,
                            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                            region_name=AWS_REGION)

userTable = dynamodb.Table(DYNAMODB_USER_TABLE)

def lambda_handler(event, context):
    response = userTable.scan()
    items = response['Items']
    for i in items:
        emailtext='Hello Subscriber!\n\n'
        stringCity=i['cities']
        cities=stringCity.split(',')
        cityWeather={}
        if i['subscribed']=='true':
            for city in cities:
                city=city.strip()
                params = dict(key='c19bc51fe37044d599d212823221511', q=city, aqi='yes', days='1', alerts='yes')
                res = requests.get('http://api.weatherapi.com/v1/forecast.json', params=params)
                if res.status_code == 200:
                    resJson=res.json()
                    currentWeather={'time':resJson['location']['localtime'],'temp':resJson['current']['temp_f'],'feelLikeTemp':resJson['current']['feelslike_f'],'curWeatherCondition':resJson['current']['condition']['text']}
                    dayWeather={'date':resJson['forecast']['forecastday'][0]['date'], 'maxTemp':resJson['forecast']['forecastday'][0]['day']['maxtemp_f'],'minTemp':resJson['forecast']['forecastday'][0]['day']['mintemp_f'],'humidity':resJson['forecast']['forecastday'][0]['day']['avghumidity'],'precip':resJson['forecast']['forecastday'][0]['day']['daily_chance_of_rain'],'weatherCondition':resJson['forecast']['forecastday'][0]['day']['condition']['text']}
                    
                else:
                    emailtext=emailtext+"One of your input cities is invalid. Consider updating your account. The invalid city is: {cityName}.\n\n".format(cityName=city)
                    continue
                string1='Here is your daily weather forcast for {cityName}.\n\n'.format(cityName=city)
                string2='The current temperature is {currentTemp} F but feels like {feelLikeTemp} F. The current weather condition is {currentCondition}.\n\n'.format(currentTemp=currentWeather['temp'],feelLikeTemp=currentWeather['feelLikeTemp'],currentCondition=currentWeather['curWeatherCondition'])
                string3='The weather for today is {dayCondition} with maximum temperature of {maxTemp} F and minimum temperature of {minTemp} F.'.format(dayCondition=dayWeather['weatherCondition'],maxTemp=dayWeather['maxTemp'],minTemp=dayWeather['minTemp'])
                string4=' Chance of rain is {precip}%.\n\n'.format(precip=dayWeather['precip'])
                emailtext=emailtext+string1+string2+string3+string4
            emailtext=emailtext+'Thank you for subscribing!'
            print(emailtext)    
            try:
                ses.send_email(
                                    Destination={
                                        'ToAddresses': [i['email']],
                                    },
                                    Message={
                                        'Body':{
                                            'Text':{
                                                'Charset':'UTF-8',
                                                'Data': emailtext,
                                            },
                                        },
                                        'Subject':{
                                            'Charset':'UTF-8',
                                            'Data': 'Storm Trooper: Weather Update',
                                        },
                                    },
                                    Source=EMAIL,
                                )
            
            except:
                continue
            
        else:
            continue
    return {
            "statusCode": 200,
            "body": 'good'
        }