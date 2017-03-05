from flask import Flask,jsonify, request
from uber_rides.client import UberRidesClient
from uber_rides.session import Session
import requests
import json

app = Flask(__name__)

# Application Server Token
SERVER_TOKEN = "XXXX-Application's Server Token-XXXXX"



# Domain model of User context shared between API.AI and WebHook
class USER_CONTEXT :
    NAME="user_context"
    START_LAT="start_latitude"
    END_LAT="end_latitude"
    START_LNG="start_longitude"
    END_LNG="end_longitude"
    FARE_ID="fare_id"
    PRODUCT_ID="product_id"
    SEAT_COUNT="seat_count"
    PRODUCT_NAME="product_name"
    REQUEST_ID="request_id"



@app.route("/agent/uber/fulfillment", methods=["POST"])
def fulfillment():
    """"
    API.AI Backend Webhook controller. Common for all the endpoints originating from API.AI agent

    :param
        request: HTTP Post Payload. API.AI webshook request format
    :return:
        response: API.AI webhook response format

    """
    #Route based on action
    apiai_req = request.get_json(silent=True, force=True)

    print("Request:")
    print(json.dumps(apiai_req, indent=4))
    action = apiai_req.get("result").get("action")
    if action == "uber.type":
        return uber_types_handler(apiai_req.get("result"),SERVER_TOKEN) #Handles ride options between Point A and Point B
    if action =="uber.estimate":
        return uber_estimate_handler(apiai_req, SERVER_TOKEN) #Handles Ride Price Estimations
    if action =="uber.confirm":
        return uber_confirm_handler(apiai_req) #Handles Final Ride Confirmations


def uber_confirm_handler(request):
    """
    :param request: API.AI Webhook format
    :return: API.AI Webhook Response format
    """
    reqeust_response = {}

    #USER_CONTEXT content processing
    context = get_context(request.get("result"),USER_CONTEXT.NAME)
    context_params = context.get("parameters")

    user_token = request.get("originalRequest").get("data").get("user").get("access_token")
    request_endpoint ="https://sandbox-api.uber.com/v1.2/requests"

    #Prepare request for the requests API POST invocation
    payload = {
        USER_CONTEXT.FARE_ID : context_params.get(USER_CONTEXT.FARE_ID),
        USER_CONTEXT.START_LAT : context_params.get(USER_CONTEXT.START_LAT),
        USER_CONTEXT.END_LAT : context_params.get(USER_CONTEXT.END_LAT),
        USER_CONTEXT.START_LNG : context_params.get(USER_CONTEXT.START_LNG),
        USER_CONTEXT.END_LNG: context_params.get(USER_CONTEXT.END_LNG),
        USER_CONTEXT.PRODUCT_ID : context_params.get(USER_CONTEXT.PRODUCT_ID)
    }

    header = {
        "Authorization": 'Bearer ' + user_token,
        "Content-Type": 'application/json',
        "Accept-Language": 'en_US'
    }

    print(json.dumps(payload, indent=4))
    print(json.dumps(header, indent=4))

    #Establishing request using reqeuests API
    response = requests.post(request_endpoint,json=payload,headers=header)
    eta = response.json().get("eta")

    #Preparing Response for API.AI
    speech = "Yay!! Your ride has been requested. E.T.A is approximately {} mins"
    speech = speech.format(eta)

    #Updating Response USER_CONTEXT with trip request Id.
    context_params[USER_CONTEXT.REQUEST_ID] = response.json().get("USER_CONTEXT.REQUEST_ID")
    reqeust_response = prepare_webhookresponse(text=speech,speech= speech,context=context)

    return reqeust_response


def uber_types_handler(result,server_token):
    """"
    Returns the Uber products types available at the user's location

    Parameters:
        arguments (json object)
            location contained in the 'source' attribute
    Return
        prodtypes_res (json object)
            speech and text of available product types

     """
    prodtypes_res = {}
    if result is not None and result!= {}:
        arguments = result.get("parameters")

        # Establising Uber Session using UBER python SDK
        session = Session(server_token=server_token)
        uber_client = UberRidesClient(session)

        #Translating Street Address to Geo Coordinates
        soruce_address = arguments.get("source")
        dest_address = arguments.get("destination")
        geo = translate_to_geolocation(soruce_address)
        destGeo = translate_to_geolocation(dest_address)

        products = get_products(geo.get("lat"),geo.get("lng"),uber_client)
        prod_names = [prod.get("display_name") for prod in products];

        speech = "Which Uber type do you prefer? You can choose from "
        text = "Select a Uber type. Available options for your location are "
        options = ", ".join(prod_names)
        print(options)

        context = get_context(result,USER_CONTEXT.NAME)
        context_parameters = context.get("parameters")
        ##context_dic = json.loads(context)
        context_parameters[USER_CONTEXT.START_LAT]=  geo.get("lat")
        context_parameters[USER_CONTEXT.START_LNG]= geo.get("lng")
        context_parameters[USER_CONTEXT.END_LAT] = destGeo.get("lat")
        context_parameters[USER_CONTEXT.END_LNG] = destGeo.get("lng")

        prodtypes_res = prepare_webhookresponse(text=text+options,speech= speech+options,context=context)

    return prodtypes_res

def uber_estimate_handler(req,server_token):
    estimate_res = {}
    result = req.get("result")
    arguments = result.get("parameters")
    user_token = req.get("originalRequest").get("data").get("user").get("access_token")
    #Fetching Context

    context = get_context(result, USER_CONTEXT.NAME)
    context_params = context.get("parameters")

    src_lat,src_lng = context_params.get(USER_CONTEXT.START_LAT),context_params.get(USER_CONTEXT.START_LNG)
    dest_lat,dest_lng = context_params.get(USER_CONTEXT.END_LAT),context_params.get(USER_CONTEXT.END_LNG)
    prod_name = context_params.get(USER_CONTEXT.PRODUCT_NAME)
    seat_cnt = 2
    if prod_name.lower() == "POOL".lower(): seat_cnt = int(arguments.get(USER_CONTEXT.SEAT_COUNT))
    # Establising Uber Session
    session = Session(server_token=server_token)
    uber_client = UberRidesClient(session)
    prod_id = get_porductid_from_name(prod_name,src_lat,src_lng,uber_client)
    estimate_endpoint = "https://api.uber.com/v1.2/requests/estimate"
    payload = {
            "product_id":prod_id,
            "start_latitude": src_lat,
            "start_longitude":src_lng,
            "end_latitude": dest_lat,
            "end_longitude": dest_lng,
            "seat_count":seat_cnt
        }
    header = {
            "Authorization" : 'Bearer '+user_token,
            "Content-Type" : 'application/json',
            "Accept-Language" : 'en_US'
        }
    print(json.dumps(payload,indent=4))
    print(json.dumps(header, indent=4))
    estimate = requests.post(estimate_endpoint,json=payload, headers=header)

    fare = estimate.json().get("fare")
    fare_id = fare.get("fare_id")
    fare_value = fare.get("value")

    speech = 'Estimated pice for your trip in Uber {} will be {}. Confirm to make a booking'
    speech = speech.format(prod_name,fare_value)


    context_params[USER_CONTEXT.PRODUCT_ID] = prod_id
    context_params[USER_CONTEXT.FARE_ID]=fare_id

    estimate_res = prepare_webhookresponse(speech,speech,context)
    return estimate_res

def get_context(result,context_name):
    response_context = {}
    if result is not None and result!={}:
        input_context = result.get("contexts")
        required_context = [context for context in input_context if context.get("name") == context_name]
        if len(required_context)>0: response_context = required_context[0]
    return response_context

def get_products(lattitude,longitude,client):

    # Products API call
    res = client.get_products(lattitude,longitude)
    return res.json.get("products");


def get_porductid_from_name(product_name,lat,lng,uber_client):

    products = get_products(lat,lng,uber_client)
    product_id = [id.get("product_id") for id in products if id.get("display_name").lower() ==product_name.lower()]

    if len(product_id)>0: return product_id[0]
    else: return ""


def translate_to_geolocation(address):
    endpoint =  "https://maps.googleapis.com/maps/api/geocode/json"
    payload = {'address': address}
    geo = {}
    response = requests.get(endpoint,params = payload)
    if response.status_code == 200:
        geo  = response.json().get("results")[0].get("geometry").get("location")

    return geo

def prepare_webhookresponse(text="",speech="",context=None):
    response_dic = {}
    response_dic["displayText"] = text
    response_dic["speech"] = speech
    if context != None:
        context_list = list()
        context_list.append(context)
        response_dic["contextOut"] = context_list

    return jsonify(response_dic)





if __name__ == "__main__":
    app.run()