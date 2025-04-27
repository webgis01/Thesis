from flask import Flask, jsonify, request
import requests
from flask_cors import CORS
import pandas as pd
import numpy as np
from statsmodels.tsa.api import SimpleExpSmoothing
import csv
import matplotlib.pyplot as plt
from sklearn.metrics import mean_squared_error, mean_absolute_error

app = Flask(__name__)
CORS(app)

THINGSPEAK_READ_API_KEY = 'A46JROYTYFVY6JQE'
THINGSPEAK_READ_URL = 'https://api.thingspeak.com/channels/2683477/feeds.json'

#default route (not important)
@app.route('/')
def home():
    return jsonify({"message": "Welcome to Flask and ThingSpeak API"})

#API endpoint for getting data from thingspeak database
#Stores the filtered data from thingspeak to a csv file named "Data.csv"
@app.route('/get_data', methods=['GET'])
def get_data():
    #The parameters used for sending a GET request
    params = {
        'api_key': THINGSPEAK_READ_API_KEY,
        'results': 8000
    }

    #Calling the get request
    response = requests.get(THINGSPEAK_READ_URL, params=params)

    # status code 200 means success
    #If the GET request is successful, then we proceed with the data filtering and saving it to a csv file.
    if response.status_code == 200:
        #We extract only the necessary data
        # In a response, maraming other stuff na kasama na irrelevant sa want natin i-measure
        # We only get the "feeds" or the actual values we need
        # ".json()" is called para maging valid format ung data once we retrieve it
        data = response.json()["feeds"]

        # Filter data: Only keep entries with entry_id >= 70 and exclude 5715 & 5716 (Unofficial data is excluded)
        filtered_data = [entry for entry in data if int(entry["entry_id"]) >= 70 and int(entry["entry_id"]) not in (5715, 5716)]

        if filtered_data:
            # Reset entry_id to start from
            # Since nag remove ng mga entry, nagreset lang ng numbering with this for loop
            for i, entry in enumerate(filtered_data, start=1):
                entry["entry_id"] = i  # Replace the original entry_id with new index

            # Save to CSV file
            with open("Data.csv", mode="w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)

                # Writing header
                writer.writerow(filtered_data[0].keys())

                # Writing data
                for entry in filtered_data:
                    writer.writerow(entry.values())

        return response.json()["feeds"], 200
    else:
        return jsonify({"message": "Failed to get data"}), 500

def mad_based_outlier(points, thresh=10): #threshold set to 10
    if len(points.shape) == 1:
        points = points[:,None]
    #calculate median
    median = np.median(points, axis=0)
    #Calculate the Deviation from the median
    diff = np.sum((points - median)**2, axis=-1)
    diff = np.sqrt(diff)
    #Calculate the Median Absolute Deviation (MAD)
    med_abs_deviation = np.median(diff)
    #Calculate Modified Z-score
    modified_z_score = 0.6745 * diff / med_abs_deviation
    #Identify the outlier
    return modified_z_score > thresh

#Endpoint na gagamitin para ma call ang pag forecast and ma display yung accuracy metrics and graphs
#Nasa endpoint na to ang main cleaning ng data.
#Nasa separate function below ang function para sa mismong forecasting and train test split, pero we call that function here also.
@app.route('/forecast_data', methods=['GET'])
def dfclean():
    #We access now yung filtered data na nakuha from the previous /get_data function
    df = pd.read_csv("Data.csv")


    df['created_at'] = pd.to_datetime(df['created_at'])
    # Define the first range of dates for data to be disregarded
    start_date1 = pd.to_datetime('2024-10-06T12:41:50+00:00')
    end_date1 = pd.to_datetime('2024-11-03T04:05:20+00:00')

    # Define the second range of dates for data to be disregarded
    start_date2 = pd.to_datetime('2024-11-11T05:27:06+00:00')
    end_date2 = pd.to_datetime('2025-02-19T05:15:47+00:00')

    # Filter out the data within both specified ranges
    df = df[
        ((df['created_at'] < start_date1) | (df['created_at'] > end_date1)) &
        ((df['created_at'] < start_date2) | (df['created_at'] > end_date2))
    ]


    #Removing Unnecessary Columns and Integrating Fields with data
    #Dito sinelect lahat ng mga columns ng devices na gumagana
    df['field2'] = pd.to_numeric(df['field2'], errors='coerce').fillna(0)
    df['field3'] = pd.to_numeric(df['field3'], errors='coerce').fillna(0)

    #gumawa ng combined field ng both devices
    df['combined_field'] = df['field2'] + df['field3'].round(2)

    #Excluded the individual field2 and 3 columns
    df = df[['created_at','entry_id','combined_field']]

    #Set Negative values to 0
    df['combined_field'] = df['combined_field'].apply(lambda x: 0 if x < 0 else x)

    # Apply the function to identify outliers
    outliers = mad_based_outlier(df['combined_field'].values)

    # Remove outliers
    df_filtered = df[~outliers]

    # Convert 'created_at' to datetime objects if it's not already
    df_filtered['created_at'] = pd.to_datetime(df['created_at'])

    """Resampling to 10-minute intervals"""
    # Resample the 'combined_field' column for every 10-minute interval
    df_resampled = df_filtered.resample('10T', on='created_at').mean().round(2)

    # Fill missing values with rolling mean
    df_resampled['combined_field'] = df_resampled['combined_field'].fillna(
        df_resampled['combined_field'].rolling(window=10, min_periods=1).mean()
    ).round(2)  #added rolling mean to fill nan values

    # Calculate the average of all data
    overall_average = df_resampled['combined_field'].mean()

    # Fill remaining missing values with the overall average
    df_resampled['combined_field'] = df_resampled['combined_field'].fillna(overall_average)

    # Calculate exponentially weighted moving average
    df_resampled['ewma'] = df_resampled['combined_field'].ewm(span=5, adjust=False).mean() #span=smoothing factor

    # Print the resampled DataFrame
    df_resampled

    """Resampling to 30-minute intervals"""
    # Resample the data to 30-minute intervals
    df_resampled_30min = df_filtered.resample('30T', on='created_at').mean().round(2)

    # Fill missing values using the same method as before
    df_resampled_30min['combined_field'] = df_resampled_30min['combined_field'].fillna(
        df_resampled_30min['combined_field'].rolling(window=10, min_periods=1).mean()
    ).round(2)

    # Fill any remaining NaN values with the overall average
    overall_average_30min = df_resampled_30min['combined_field'].mean()
    df_resampled_30min['combined_field'] = df_resampled_30min['combined_field'].fillna(overall_average_30min)

    # Display the resampled data
    df_resampled_30min

    # Calculate exponentially weighted moving average for 30-minute data
    df_resampled_30min['ewma_30min'] = df_resampled_30min['combined_field'].ewm(span=5, adjust=False).mean()

    """Resampling to 60-minute intervals"""
    # Resample the data to 60-minute intervals
    df_resampled_60min = df_filtered.resample('60T', on='created_at').mean().round(2)

    # Fill missing values using the same method as before
    df_resampled_60min['combined_field'] = df_resampled_60min['combined_field'].fillna(
        df_resampled_60min['combined_field'].rolling(window=10, min_periods=1).mean()
    ).round(2)

    # Fill any remaining NaN values with the overall average
    overall_average_60min = df_resampled_60min['combined_field'].mean()
    df_resampled_60min['combined_field'] = df_resampled_60min['combined_field'].fillna(overall_average_60min)

    # Calculate exponentially weighted moving average for 60-minute data
    df_resampled_60min['ewma_60min'] = df_resampled_60min['combined_field'].ewm(span=5, adjust=False).mean()


    df_resampled.to_csv('cleaned_data.csv', index=True)
    print("Cleaned data saved to 'cleaned_data.csv'")

    #Afterwards, call the train test split and actual forecasting
    next_forecast_10min, formatted_time_10min, next_timestamp_10min = train_test_split_and_forecast(df_resampled)
    next_forecast_30min, formatted_time_30min,next_timestamp_30min = train_test_split_and_forecast_30min(df_resampled_30min,next_forecast_10min, next_timestamp_10min)
    next_forecast_60min, formatted_time_60min,next_timestamp_60min = train_test_split_and_forecast_60min(df_resampled_60min,next_forecast_30min, next_timestamp_30min)

    return jsonify({
    "forecast_10min": next_forecast_10min,
    "timestamp_10min": formatted_time_10min,
    "forecast_30min": next_forecast_30min,
    "timestamp_30min": formatted_time_30min,
    "forecast_60min": next_forecast_60min,
    "timestamp_60min": formatted_time_60min
    }), 200



# Calculate MAPE
def mean_absolute_percentage_error(y_true, y_pred):
    y_true, y_pred = np.array(y_true), np.array(y_pred)
    mask = y_true != 0  # Create a mask to exclude zero values from y_true
    return np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100

def train_test_split_and_forecast(df_resampled):

    # Split the data into training and testing sets (80% training, 20% testing)
    train_data = df_resampled[:int(0.8 * len(df_resampled))]
    test_data = df_resampled[int(0.8 * len(df_resampled)):]

    # Define a range of alpha values to test
    alphas = np.arange(0.1, 1, 0.1)  # Values from 0.1 to 0.9 in steps of 0.1

    # Initialize variables to store the best alpha and corresponding error metrics
    best_alpha = None
    best_rmse = float('inf')  # Initialize with a very large value
    best_mape = float('inf')

    # Iterate through alpha values and calculate error metrics
    for alpha in alphas:
        forecasted_values = []
        for i in range(len(test_data)):
            if i == 0:
                # Use 'ewma' for the initial value
                last_value = train_data['ewma'].iloc[-1]
            else:
                last_value = forecasted_values[-1]

            # Use 'ewma' for the actual values in the test set
            next_forecast = alpha * test_data['ewma'].iloc[i-1] + (1 - alpha) * last_value
            forecasted_values.append(next_forecast)

        # Calculate RMSE and MAPE for the current alpha using 'ewma'
        rmse = np.sqrt(mean_squared_error(test_data['ewma'], forecasted_values))
        mape = mean_absolute_percentage_error(test_data['ewma'], forecasted_values)

        # Update best_alpha, best_rmse, and best_mape if current alpha gives better results
        if mape < best_mape and rmse < best_rmse:
            best_alpha = alpha
            best_rmse = rmse
            best_mape = mape

    # Create a DataFrame for the actual values using 'ewma'
    actual_df = pd.DataFrame({'Actual': test_data['ewma'].values}, index=test_data.index)

    # Create a DataFrame for the forecasted values, using the same index as actual_df
    forecast_df = pd.DataFrame({'Forecasted': forecasted_values}, index=test_data.index)

    # Concatenate the two DataFrames to create a single table
    comparison_table = pd.concat([actual_df, forecast_df], axis=1)

    # Display the table
    print(comparison_table)

    # Print the optimal alpha and corresponding error metrics
    print(f"Optimal alpha: {best_alpha}")
    print(f"Best RMSE: {best_rmse}")
    print(f"Best MAPE: {best_mape}")

    # 10-minute forecast
    last_value_10min = forecasted_values[-1]
    next_forecast_10min = best_alpha * test_data['combined_field'].iloc[-1] + (1 - best_alpha) * last_value_10min
    next_forecast_10min = round(next_forecast_10min, 3)
    next_timestamp_10min = test_data.index[-1] + pd.Timedelta(minutes=10)
    formatted_time_10min = next_timestamp_10min.strftime('%I:%M:%S %p')
    print(f"10-minute forecast: {next_forecast_10min} at {formatted_time_10min}")

    return next_forecast_10min, formatted_time_10min, next_timestamp_10min


def train_test_split_and_forecast_30min(df_resampled_30min, next_forecast_10min, next_timestamp_10min):
    # Split the data into training and testing sets
    train_data_30min = df_resampled_30min[:int(0.8 * len(df_resampled_30min))]
    test_data_30min = df_resampled_30min[int(0.8 * len(df_resampled_30min)):]

    # ... (rest of your SES forecasting code, but using train_data_30min and test_data_30min)
    alphas = np.arange(0.1, 1, 0.1)
    best_alpha_30min = None
    best_rmse_30min = float('inf')
    best_mape_30min = float('inf')

    for alpha in alphas:
        forecasted_values_30min = []
        for i in range(len(test_data_30min)):
            if i == 0:
                # Use 'ewma_30min' for the initial value
                last_value = train_data_30min['ewma_30min'].iloc[-1]
            else:
                last_value = forecasted_values_30min[-1]
            # Use 'ewma_30min' for the actual values in the test set
            next_forecast = alpha * test_data_30min['ewma_30min'].iloc[i-1] + (1 - alpha) * last_value
            forecasted_values_30min.append(next_forecast)

        rmse_30min = np.sqrt(mean_squared_error(test_data_30min['ewma_30min'], forecasted_values_30min))
        mape_30min = mean_absolute_percentage_error(test_data_30min['ewma_30min'], forecasted_values_30min)

        if rmse_30min < best_rmse_30min and mape_30min < best_mape_30min:
            best_alpha_30min = alpha
            best_rmse_30min = rmse_30min
            best_mape_30min = mape_30min

    print(f"Optimal alpha (30-min): {best_alpha_30min}")
    print(f"Best RMSE (30-min): {best_rmse_30min}")
    print(f"Best MAPE (30-min): {best_mape_30min}")

    actual_df_30min = pd.DataFrame({'Actual': test_data_30min['ewma_30min'].values}, index=test_data_30min.index) # Use 'ewma_30min'
    forecast_df_30min = pd.DataFrame({'Forecasted': forecasted_values_30min}, index=test_data_30min.index)
    comparison_table_30min = pd.concat([actual_df_30min, forecast_df_30min], axis=1)
    comparison_table_30min


    # 30-minute extended forecast
    last_value_30min = forecasted_values_30min[-1]
    next_timestamp_30min = test_data_30min.index[-1] + pd.Timedelta(minutes=30)

    # Check if 10-minute and 30-minute forecasts have the same interval
    if next_timestamp_10min == next_timestamp_30min:
        next_forecast_30min = next_forecast_10min  # Use 10-minute forecast value
    else:
        next_forecast_30min = best_alpha_30min * test_data_30min['combined_field'].iloc[-1] + (1 - best_alpha_30min) * last_value_30min
        next_forecast_30min = round(next_forecast_30min, 3)

    print(f"30-minute forecast: {next_forecast_30min} at {next_timestamp_30min.strftime('%I:%M:%S %p')}")

    formatted_time_30min = next_timestamp_30min.strftime('%I:%M:%S %p')

    return next_forecast_30min, formatted_time_30min, next_timestamp_30min

def train_test_split_and_forecast_60min(df_resampled_60min,next_forecast_30min,next_timestamp_30min):
    # Split the data into training and testing sets
    train_data_60min = df_resampled_60min[:int(0.8 * len(df_resampled_60min))]
    test_data_60min = df_resampled_60min[int(0.8 * len(df_resampled_60min)):]

    # ... (rest of your SES forecasting code, but using train_data_60min and test_data_60min)
    alphas = np.arange(0.1, 1, 0.1)
    best_alpha_60min = None
    best_rmse_60min = float('inf')
    best_mape_60min = float('inf')

    for alpha in alphas:
        forecasted_values_60min = []
        for i in range(len(test_data_60min)):
            if i == 0:
                # Use 'ewma_60min' for the initial value
                last_value = train_data_60min['ewma_60min'].iloc[-1]
            else:
                last_value = forecasted_values_60min[-1]
            # Use 'ewma_60min' for the actual values in the test set
            next_forecast = alpha * test_data_60min['ewma_60min'].iloc[i-1] + (1 - alpha) * last_value
            forecasted_values_60min.append(next_forecast)

        # Calculate RMSE and MAPE using 'ewma_60min'
        rmse_60min = np.sqrt(mean_squared_error(test_data_60min['ewma_60min'], forecasted_values_60min))
        mape_60min = mean_absolute_percentage_error(test_data_60min['ewma_60min'], forecasted_values_60min)

        if rmse_60min < best_rmse_60min and mape_60min < best_mape_60min:
            best_alpha_60min = alpha
            best_rmse_60min = rmse_60min
            best_mape_60min = mape_60min

    print(f"Optimal alpha (60-min): {best_alpha_60min}")
    print(f"Best RMSE (60-min): {best_rmse_60min}")
    print(f"Best MAPE (60-min): {best_mape_60min}")

    # Create DataFrames using 'ewma_60min'
    actual_df_60min = pd.DataFrame({'Actual': test_data_60min['ewma_60min'].values}, index=test_data_60min.index)  # Use 'ewma_60min'
    forecast_df_60min = pd.DataFrame({'Forecasted': forecasted_values_60min}, index=test_data_60min.index)
    comparison_table_60min = pd.concat([actual_df_60min, forecast_df_60min], axis=1)
    comparison_table_60min


    # 60-minute extended forecast
    last_value_60min = forecasted_values_60min[-1]
    next_forecast_60min = best_alpha_60min * test_data_60min['combined_field'].iloc[-1] + (1 - best_alpha_60min) * last_value_60min
    next_forecast_60min = round(next_forecast_60min, 3)
    next_timestamp_60min = test_data_60min.index[-1] + pd.Timedelta(minutes=60)

    # Check if 60-minute and 30-minute forecasts have the same interval
    if next_timestamp_30min == next_timestamp_60min:
        next_forecast_60min = next_forecast_30min  # Use 30-minute forecast value
    else:
        next_forecast_60min = best_alpha_60min * test_data_60min['combined_field'].iloc[-1] + (1 - best_alpha_60min) * last_value_60min
        next_forecast_60min = round(next_forecast_60min, 3)

    formatted_time_60min = next_timestamp_60min.strftime('%I:%M:%S %p')
    print(f"60-minute forecast: {next_forecast_60min} at {formatted_time_60min}")

    return next_forecast_60min, formatted_time_60min, next_timestamp_60min

def get_latest_per_device(sorted_entries):
    latest_entries = {
        'field2': None,
        'field3': None,
    }

    for entry in sorted_entries:
        if entry.get('entry_id') == 4542:
            latest_entries['field2'] = entry.get('field2')
        elif entry.get('entry_id') == 4543:
            latest_entries['field3'] = entry.get('field3')

        # Stop early if both are found
        if all(value is not None for value in latest_entries.values()):
            break

    print(latest_entries)
    return [latest_entries[field] for field in latest_entries]



@app.route('/get_latest', methods=['GET'])
def get_latest():

     # Dictionary to store the latest entry for each device
    latest_entries = {
        'field2': None,
        'field3': None,
    }
    params = {
        'api_key': THINGSPEAK_READ_API_KEY,
        'results': 8000
    }

    response = requests.get(THINGSPEAK_READ_URL, params=params)
    feeds = response.json()["feeds"]

    latest_entries =  get_latest_per_device(feeds)
    print(latest_entries)
    return latest_entries,200

if __name__ == '__main__':
    app.run(debug=True)
