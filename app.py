#!flask/bin/python
import sys, os
from env import AWS_ACCESS_KEY, AWS_SECRET_ACCESS_KEY, AWS_REGION, API_KEY, PHOTOGALLERY_S3_BUCKET_NAME, DYNAMODB_TABLE, DYNAMODB_USER_TABLE, KEY, SALT, EMAIL
from flask import Flask, jsonify, abort, request, make_response, send_file, url_for, flash, session, Response, render_template, redirect
import exifread
import uuid
import boto3
from boto3.dynamodb.conditions import Key, Attr
from datetime import datetime
import pytz
import bcrypt
import requests
from itsdangerous import URLSafeTimedSerializer
import csv
import mimetypes
import pandas as pd
import plotly
import plotly.graph_objects as go
from plotly.subplots import make_subplots


app = Flask(__name__, static_url_path="")

dynamodb = boto3.resource('dynamodb', aws_access_key_id=AWS_ACCESS_KEY,
                            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                            region_name=AWS_REGION)

userTable = dynamodb.Table(DYNAMODB_USER_TABLE)

UPLOAD_FOLDER = os.path.join(app.root_path,'static','media')
ALLOWED_EXTENSIONS = set(['png', 'jpg', 'jpeg'])

csvFilename='weather_data.csv'

@app.errorhandler(400)
def bad_request(error):
    """ 400 page route.

    get:
        description: Endpoint to return a bad request 400 page.
        responses: Returns 400 object.
    """
    return make_response(jsonify({'error': 'Bad request'}), 400)

@app.errorhandler(404)
def not_found(error):
    """ 404 page route.

    get:
        description: Endpoint to return a not found 404 page.
        responses: Returns 404 object.
    """
    return make_response(jsonify({'error': 'Not found'}), 404)


@app.route('/signup', methods=['GET', 'POST'])
def signup_page():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        if (password != request.form['password1']):
            return redirect('/signup')

        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
        cities = request.form['city']
        subscribed = request.form['subscribed']
        print(subscribed)
        firstName = request.form['firstname']
        lastName = request.form['lastname']
        userName = request.form['username']

        response = userTable.query(
            KeyConditionExpression=Key('email').eq(email)
        )
        results = response['Items']
        if  len(results) != 0:
            if results[0]['emailconfirmed'] == 'yes':
                return redirect('/login')
            else:
                userTable.update_item(
                Key={
                    'email': email
                },
                UpdateExpression= "SET password=:h",
                ExpressionAttributeValues={
                    ':h': hashed,
                })
        else:
            userTable.put_item( 
            Item={
                    "email": email,
                    "password": hashed,
                    "emailconfirmed":'no',
                    "cities": cities,
                    "subscribed": subscribed,
                    "firstname": firstName,
                    "lastname": lastName,
                    "username": userName
                }
            )

        serializer = URLSafeTimedSerializer(KEY)
        token = serializer.dumps(email, salt=SALT)
        
        # Create a new SES resource and specify a region.
        ses = boto3.client('ses',
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY)
        SENDER = EMAIL
        RECEIVER = email

        # Try to send the email.
        # Provide the contents of the email.
        try:
            response = ses.send_email(
            Destination={
                'ToAddresses': [RECEIVER],
             },
             Message={
                    'Body': {
                        'Text': {
                            'Data': 'Hello, please confirm your email using this link: localhost:5000/confirmemail/' + token,
                                },
                            },
                    'Subject': {
                        'Data': 'Storm Trooper Email Confirmation'
                    },
            },
            Source=SENDER
            )
        except:
            return render_template('signup.html')

        return render_template('login.html')
    else:
        return render_template('signup.html')

@app.route('/confirmemail/<string:token>', methods = ['GET'])
def confirmemail(token):
    serializer = URLSafeTimedSerializer(KEY)
    try:
        email = serializer.loads(
            token,
            salt=SALT,
            max_age=600
        )

        userTable.update_item(
        Key={
            'email': email
        },
        UpdateExpression= "SET emailconfirmed=:c",
        ExpressionAttributeValues={
            ':c': 'yes',
        })

    # Redirect to signup if the link is expired.
    except Exception as e:
        return redirect('/signup')
    else:
        return redirect('/login')

@app.route('/logout', methods=['GET'])
def logout():
    try:
        serializer = URLSafeTimedSerializer(KEY)
        email = serializer.loads(
            request.cookies.get('loginID'),
            salt=SALT,
            max_age=300
        )
    except Exception as e:
        return redirect('/login')

    response = make_response(redirect('/login'))
    response.set_cookie('loginID', 'deleted', expires=0)
    return response


@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        password = request.form['password']
        email = request.form['emailID']
        
        response = userTable.query(
            KeyConditionExpression=Key('email').eq(email)
        )

        results = response['Items']
        if len(results) == 0 or results[0]['emailconfirmed'] == 'no':
            return redirect('/signup')
        hashed = results[0]['password']
        if bcrypt.checkpw(password.encode(), bytes(hashed)):
            serializer = URLSafeTimedSerializer(KEY)
            token = serializer.dumps(email, salt=SALT)
            response = make_response(redirect('/'))
            response.set_cookie('loginID', token)
            return response
        else:
            return redirect('/login')
    else:
        return render_template("login.html")


@app.route('/delete_account', methods=['GET'])
def delete_account():
    try:
        serializer = URLSafeTimedSerializer(KEY)
        email = serializer.loads(
            request.cookies.get('loginID'),
            salt=SALT,
            max_age=300
        )
    except Exception as e:
        return redirect('/login')

    userTable.delete_item(
        Key={
                "email": email
            }
        )

    response = make_response(redirect('/login'))
    response.set_cookie('loginID', 'deleted', expires=0)
    return response

@app.route('/', methods=['GET'])
def home_page():
    
    try: #check to make sure thye have a cookie and logged in
        serializer = URLSafeTimedSerializer(KEY)
        email = serializer.loads(
            request.cookies.get('loginID'),
            salt=SALT,
            # max_age=300
        )
    except Exception as e: #if not make them login
        return redirect('/login')

    response = userTable.get_item(
            Key={
                "email": email  
                }          
            ) 

    results = response['Item']
    userName = results['username']

    stringCity=response['Item']['cities'] #get user's list of cities
    cities=stringCity.split(',')
    cityWeather={}
    for city in cities: 
        city=city.strip()
        #q is the city name
        #aqi has value of yes or no and tells the api whether you want air quality data
        #days: number of days of future info you want. 1 day meany 24 hours so the fulle current day, 2 days would be today and tomorrow
        #alerts: include weather alerts yes or no
        params = dict(key=API_KEY, q=city, aqi='yes', days='1', alerts='yes') #set up params for api call
        res = requests.get('http://api.weatherapi.com/v1/forecast.json', params=params) #call api
        if res.status_code == 200:
            resJson=res.json() #convert json object to pyhton dictionary

            #get all the current data for the city
            currentWeather={'city':city,'time':resJson['location']['localtime'],'temp':resJson['current']['temp_f'],'feelLikeTemp':resJson['current']['feelslike_f'],'curWeatherCondition':resJson['current']['condition']['text'],'picture':resJson['current']['condition']['icon'],'humidity':resJson['current']['humidity'],'windSpeed':resJson['current']['wind_mph'],'aqi''feelLikeTemp':resJson['current']['air_quality']['us-epa-index']}
            #get data for the overall day
            dayWeather={'city':city,'date':resJson['forecast']['forecastday'][0]['date'], 'maxTemp':resJson['forecast']['forecastday'][0]['day']['maxtemp_f'],'minTemp':resJson['forecast']['forecastday'][0]['day']['mintemp_f'],'humidity':resJson['forecast']['forecastday'][0]['day']['avghumidity'],'precip':resJson['forecast']['forecastday'][0]['day']['daily_chance_of_rain'],'weatherCondition':resJson['forecast']['forecastday'][0]['day']['condition']['text'],'picture':resJson['forecast']['forecastday'][0]['day']['condition']['text'],'maxWind':resJson['forecast']['forecastday'][0]['day']['maxwind_mph'],'aqi':resJson['forecast']['forecastday'][0]['day']['air_quality']['us-epa-index']}
            weatherOverTime={}
            #get data for every hour of the current day
            for index,i in enumerate(resJson['forecast']['forecastday'][0]['hour']):
                weatherOverTime[index]={'city':city,'hour':float(index), 'time':i['time'],'temp':i['temp_f'],'feelLikeTemp':i['feelslike_f'],'curWeatherCondition':i['condition']['text'], 'windSpeed':i['wind_mph'],'humidity':i['humidity'], 'chanceOfPrecip':i['chance_of_rain'],'aqi':i['air_quality']['us-epa-index']}
            cityWeather[city]={'currentWeather':currentWeather, 'weatherForDay':dayWeather,'weatherOverTime':weatherOverTime}
        else:
            continue
    
    if cityWeather: #if this object exists write it to a csv and generate plots
        keys = weatherOverTime[0].keys()

        f=open(csvFilename,'w')
        for i in cityWeather.keys():
            for time in cityWeather[i]['weatherOverTime'].keys():
                dict_writer = csv.DictWriter(f,keys,lineterminator='\n')
                if f.tell()==0:
                    dict_writer.writeheader()
                    dict_writer.writerow(cityWeather[i]['weatherOverTime'][time])
                else:
                    dict_writer.writerow(cityWeather[i]['weatherOverTime'][time])
        f.close()
        data=pd.read_csv('weather_data.csv')
        cities=data['city'].unique()

        data_temp=data.pivot(index='hour', columns = 'city', values = 'temp')
        data_feelLikeTemp=data.pivot(index='hour', columns = 'city', values = 'feelLikeTemp')
        data_humidity=data.pivot(index='hour', columns = 'city', values = 'humidity')
        data_windSpeed=data.pivot(index='hour', columns = 'city', values = 'windSpeed')
        data_aqi=data.pivot(index='hour', columns = 'city', values = 'aqi')
        data_precip=data.pivot(index='hour', columns = 'city', values = 'chanceOfPrecip')
       
        fig_temp = go.Figure()
        fig_feelLikeTemp = go.Figure()
        fig_humidity = go.Figure()
        fig_windSpeed = go.Figure()
        fig_aqi = go.Figure()
        fig_precip = go.Figure()
        fig_subplots=make_subplots( rows=3, cols=2, subplot_titles=("Temperature Over Time", "Feel Like Temperature Over Time","Humidity Over Time", "Wind Speed Over Time", "AQI Over Time", "Chance of Precipitation Over Time"))
        cols = plotly.colors.DEFAULT_PLOTLY_COLORS
        num=0
        for city in cities:
            fig_temp.add_trace(go.Scatter(x=data_temp.index.values.tolist(), y=data_temp[city].tolist(),
                                        mode='lines',
                                        name=city, 
                                        text=data_temp[city].tolist(),
                                        line_width=2))
            fig_subplots.add_trace(go.Scatter(x=data_temp.index.values.tolist(), y=data_temp[city].tolist(),
                                        mode='lines',
                                        name=city, 
                                        text=data_temp[city].tolist(),
                                        legendgroup=city,
                                        line_width=2,line_color=cols[num],showlegend=False), 
                                        row=1, col=1)
            
            fig_feelLikeTemp.add_trace(go.Scatter(x=data_feelLikeTemp.index.values.tolist(), y=data_feelLikeTemp[city].tolist(),
                                        mode='lines',
                                        name=city, 
                                        text=data_feelLikeTemp[city].tolist(),
                                        line_width=2))
            fig_subplots.add_trace(go.Scatter(x=data_feelLikeTemp.index.values.tolist(), y=data_feelLikeTemp[city].tolist(),
                                        mode='lines',
                                        name=city, 
                                        legendgroup=city,
                                        text=data_feelLikeTemp[city].tolist(),
                                        line_width=2,line_color=cols[num],showlegend=False), row=1, col=2)
            fig_humidity.add_trace(go.Scatter(x=data_humidity.index.values.tolist(), y=data_humidity[city].tolist(),
                                        mode='lines',
                                        name=city, 
                                        text=data_humidity[city].tolist(),
                                        line_width=2))
            fig_subplots.add_trace(go.Scatter(x=data_humidity.index.values.tolist(), y=data_humidity[city].tolist(),
                                        mode='lines',
                                        name=city, 
                                        legendgroup=city,
                                        text=data_humidity[city].tolist(),
                                        line_width=2,line_color=cols[num], showlegend=False), row=2, col=1)
            fig_windSpeed.add_trace(go.Scatter(x=data_windSpeed.index.values.tolist(), y=data_windSpeed[city].tolist(),
                                        mode='lines',
                                        name=city, 
                                        text=data_windSpeed[city].tolist(),
                                        line_width=2))
            fig_subplots.add_trace(go.Scatter(x=data_windSpeed.index.values.tolist(), y=data_windSpeed[city].tolist(),
                                        mode='lines',
                                        name=city, 
                                        legendgroup=city,
                                        text=data_windSpeed[city].tolist(),
                                        line_width=2,line_color=cols[num],showlegend=False), row=2, col=2)
            fig_aqi.add_trace(go.Scatter(x=data_aqi.index.values.tolist(), y=data_aqi[city].tolist(),
                                        mode='lines',
                                        name=city, 
                                        text=data_aqi[city].tolist(),
                                        line_width=2))
            fig_subplots.add_trace(go.Scatter(x=data_aqi.index.values.tolist(), y=data_aqi[city].tolist(),
                                        mode='lines',
                                        name=city, 
                                        legendgroup=city,
                                        text=data_aqi[city].tolist(),
                                        line_width=2,line_color=cols[num],showlegend=False),row=3,col=1)
            fig_precip.add_trace(go.Scatter(x=data_precip.index.values.tolist(), y=data_precip[city].tolist(),
                                        mode='lines',
                                        name=city, 
                                        text=data_precip[city].tolist(),
                                        line_width=2))
            fig_subplots.add_trace(go.Scatter(x=data_precip.index.values.tolist(), y=data_precip[city].tolist(),
                                        mode='lines',
                                        name=city, 
                                        legendgroup=city,
                                        text=data_precip[city].tolist(),
                                        line_width=2,line_color=cols[num]), row=3,col=2)
            num+=1
        fig_subplots.update_layout(title={'text':'Weather Charts',
                                    'xanchor': 'center',
                                    'x':0.5},
                            plot_bgcolor="#FBFCFC",
                            paper_bgcolor="#EAEDED",)
        fig_subplots.write_image(r'static/WeatherCharts.png')
        fig_temp.update_layout(title={'text':'Temperatures Over Time',
                                    'xanchor': 'center',
                                    'x':0.5},
                            xaxis_title='Time (Hours Throughout the Day)',
                            yaxis_title='Temperature (F)',
                            plot_bgcolor="#FBFCFC",
                            paper_bgcolor="#EAEDED",
                            showlegend=True,)
        fig_temp.update_xaxes(rangeslider_visible=True, showgrid=True)#, ticklabelmode="period", tickformat="%X")
        fig_temp=fig_temp.to_html()

        fig_feelLikeTemp.update_layout(title={'text':'Feel Like Temperatures Over Time',
                                    'xanchor': 'center',
                                    'x':0.5},
                            xaxis_title='Time (Hours Throughout the Day)',
                            yaxis_title='Temperature (F)',
                            plot_bgcolor="#FBFCFC",
                            paper_bgcolor="#EAEDED",
                            showlegend=True,)
        fig_feelLikeTemp.update_xaxes(rangeslider_visible=True, showgrid=True)#, ticklabelmode="period", tickformat="%X")
        fig_feelLikeTemp=fig_feelLikeTemp.to_html()

        fig_humidity.update_layout(title={'text':'Humidity Over Time',
                                    'xanchor': 'center',
                                    'x':0.5},
                            xaxis_title='Time (Hours Throughout the Day)',
                            yaxis_title='Humidity',
                            plot_bgcolor="#FBFCFC",
                            paper_bgcolor="#EAEDED",
                            showlegend=True,)
        fig_humidity.update_xaxes(rangeslider_visible=True, showgrid=True)#, ticklabelmode="period", tickformat="%X")
        fig_humidity=fig_humidity.to_html()

        fig_windSpeed.update_layout(title={'text':'Wind Speed Over Time',
                                    'xanchor': 'center',
                                    'x':0.5},
                            xaxis_title='Time (Hours Throughout the Day)',
                            yaxis_title='Speed (mph)',
                            plot_bgcolor="#FBFCFC",
                            paper_bgcolor="#EAEDED",
                            showlegend=True,)
        fig_windSpeed.update_xaxes(rangeslider_visible=True, showgrid=True)#, ticklabelmode="period", tickformat="%X")
        fig_windSpeed=fig_windSpeed.to_html()

        fig_aqi.update_layout(title={'text':'AQI Over Time',
                                    'xanchor': 'center',
                                    'x':0.5},
                            xaxis_title='Time (Hours Throughout the Day)',
                            yaxis_title='AQI',
                            plot_bgcolor="#FBFCFC",
                            paper_bgcolor="#EAEDED",
                            showlegend=True,)
        fig_aqi.update_xaxes(rangeslider_visible=True, showgrid=True)#, ticklabelmode="period", tickformat="%X")
        fig_aqi=fig_aqi.to_html()

        fig_precip.update_layout(title={'text':'Chance of Precipiation Over Time',
                                    'xanchor': 'center',
                                    'x':0.5},
                            xaxis_title='Time (Hours Throughout the Day)',
                            yaxis_title='Chance of Precipitation (%)',
                            plot_bgcolor="#FBFCFC",
                            paper_bgcolor="#EAEDED",
                            showlegend=True,)
        fig_precip.update_xaxes(rangeslider_visible=True, showgrid=True)#, ticklabelmode="period", tickformat="%X")
        fig_precip=fig_precip.to_html()


        figures={'fig_temp':fig_temp, 'fig_feelLikeTemp':fig_feelLikeTemp, 'fig_humidity': fig_humidity, 'fig_windSpeed':fig_windSpeed, 'fig_aqi':fig_aqi, 'fig_precip':fig_precip}

        return render_template('index.html',weatherDict=cityWeather, username=userName, figs=figures)
            #render_template('index.html',weatherDict=cityWeather, username=userName)
    return render_template('index.html')
@app.route('/downloadCSV', methods=['GET']) #download csv generated from homepage
def download_csv():

    return send_file(csvFilename,as_attachment=True)

@app.route('/generateCharts', methods=['GET']) #odwnload plots generated from homepage
def download_charts():
    try:
        return send_file(r'static/WeatherCharts.png',as_attachment=True)
    except:
        return redirect('/')

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=5000)
