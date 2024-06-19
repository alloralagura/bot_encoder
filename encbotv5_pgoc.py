import datetime
import requests
import json
from openai import OpenAI
import time
import threading
import tkinter as tk
from tkinter import messagebox
from tkinter import scrolledtext
import re
from opencage.geocoder import OpenCageGeocode
from geopy.geocoders import Nominatim

log_file_name = None

# Define access token, page ID, and OpenAI details
ACCESS_TOKEN = ""
OPENAI_API_KEY = ""
OPENAI_ASSISTANT_ID = "asst_FjdCSwMb0V5h9yt9TERuh7CL"
PAGE_NAME = ""
ID_IT_TAG = None
ORDER_IT_TAG = None
SHOP_ID = None

CUTOFF_TIME = datetime.datetime.strptime('16:00:00', '%H:%M:%S').time()

# Initialize OpenAI client
openai_client = OpenAI(api_key=OPENAI_API_KEY)


def log_to_ui(text):
    output_text_widget.insert(tk.END, text + "\n")
    output_text_widget.see(tk.END)
    if log_file_name:
        with open(log_file_name, "a") as log_file:
            log_file.write(text + "\n")


def get_page_id(page_name, access_token):
    global PAGE_ID  # Declare PAGE_ID as a global variable
    base_url = "https://pancake.ph/api/v1/pages?access_token={}"
    url = base_url.format(access_token)
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            pages = data.get("categorized", {}).get("activated", [])
            for page in pages:
                if page["name"].lower() == page_name.lower():
                    PAGE_ID = page["id"]  # Set PAGE_ID value
                    return
            log_to_ui("Page not found.")
        else:
            log_to_ui(f"Failed to retrieve data. Status code: {response.status_code}")
    except Exception as e:
        log_to_ui(f"An error occurred: {e}")


# Function to get ID_IT_TAG, ORDER_IT_TAG, SHOP_ID
def get_page_settings():
    global ID_IT_TAG, ORDER_IT_TAG, SHOP_ID
    base_url = "https://pancake.ph/api/v1/pages/{}/settings?access_token={}"
    url = base_url.format(PAGE_ID, ACCESS_TOKEN)
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            SHOP_ID = data.get("shop_id", None)
            if SHOP_ID is not None:
                log_to_ui(f"Shop ID: {SHOP_ID}")
            else:
                log_to_ui("Shop ID not found.")

            tags = data["settings"].get("tags", [])
            IT_tag = next((tag for tag in tags if tag["text"] == "IT"), None)
            if IT_tag:
                ID_IT_TAG = IT_tag["id"]
                ORDER_IT_TAG = tags.index(IT_tag)
                log_to_ui(f"ID_IT_TAG: {ID_IT_TAG}")
                log_to_ui(f"ORDER_IT_TAG: {ORDER_IT_TAG}")
            else:
                log_to_ui("Tag with name 'IT' not found.")
        else:
            log_to_ui(f"Failed to retrieve data. Status code: {response.status_code}")
    except Exception as e:
        log_to_ui(f"An error occurred: {e}")


def get_exported_tag_id(SHOP_ID, ACCESS_TOKEN):
    try:
        url = f"https://pos.pages.fm/api/v1/shops/{SHOP_ID}?access_token={ACCESS_TOKEN}&load_promotion=1"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        shop = data.get("shop", {})
        order_tags = shop.get("order_tags", [])
        for tag in order_tags:
            if tag.get("name") == "EXPORTED":
                return tag.get("id")
        return None
    except requests.exceptions.RequestException as e:
        log_to_ui(f"HTTP request failed: {e}")
        return None
    except ValueError as e:
        log_to_ui(f"Failed to parse JSON response: {e}")
        return None


def get_encoded_tag_id(SHOP_ID, ACCESS_TOKEN):
    try:
        url = f"https://pos.pages.fm/api/v1/shops/{SHOP_ID}?access_token={ACCESS_TOKEN}&load_promotion=1"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        shop = data.get("shop", {})
        order_tags = shop.get("order_tags", [])
        for tag in order_tags:
            if tag.get("name") == "ENCODED":
                return tag.get("id")
        return None
    except requests.exceptions.RequestException as e:
        log_to_ui(f"HTTP request failed: {e}")
        return None
    except ValueError as e:
        log_to_ui(f"Failed to parse JSON response: {e}")
        return None


def get_conversations(START_DATE, END_DATE):
    get_conversations_url = f"https://pancake.ph/api/v1/pages/{PAGE_ID}/conversations?unread_first=true&type=PHONE,DATE:{START_DATE}+-+{END_DATE},INBOX&mode=OR&tags=%22ALL%22&except_tags=[{ORDER_IT_TAG}]&access_token={ACCESS_TOKEN}&from_platform=web"
    response = requests.get(get_conversations_url)
    if response.status_code == 200:
        data = response.json()
        conversations = data.get('conversations', [])
        if not conversations:
            log_to_ui("Warning: Status code 200, but no conversations found.")
            log_to_ui(get_conversations_url)
        return conversations
    else:
        log_to_ui(f"Error: {response.status_code}")
        log_to_ui(get_conversations_url)
        return None


def get_messages(conversation_id, customer_id):
    url = f"https://pancake.ph/api/v1/pages/{PAGE_ID}/conversations/{conversation_id}/messages"
    params = {
        "customer_id": customer_id,
        "access_token": ACCESS_TOKEN,
        "user_view": "true",
        "is_new_api": "true"
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        return data['messages']
    else:
        log_to_ui(f"Error: {response.status_code}")
        return None


def send_to_openai(message_content):
    chat = openai_client.beta.threads.create(
        messages=[
            {
                "role": "user",
                "content": message_content
            }
        ]
    )
    run = openai_client.beta.threads.runs.create(thread_id=chat.id, assistant_id=OPENAI_ASSISTANT_ID)
    while run.status != "completed":
        run = openai_client.beta.threads.runs.retrieve(thread_id=chat.id, run_id=run.id)
        datetime.timedelta(seconds=0.5)
    message_response = openai_client.beta.threads.messages.list(thread_id=chat.id)
    messages = message_response.data
    latest_message = messages[0]
    return latest_message.content[0].text.value

def get_last_sku(message_text):
    # Find the last SKU in the message using a regular expression
    sku_matches = re.findall(r'\b[\d\w\+]+=\d+\b', message_text)
    if not sku_matches:
        return None
    return sku_matches[-1]  # Return the last matched SKU

    

def get_latest_order_info(conversation_id, customer_id):
    url = f"https://pancake.ph/api/v1/pages/{PAGE_ID}/conversations/{conversation_id}/messages/recent_orders"
    params = {
        "customer_id": customer_id,
        "access_token": ACCESS_TOKEN
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        recent_orders = data.get('recent_orders', [])
        if recent_orders:
            latest_order = recent_orders[0]
            return latest_order
        else:
            log_to_ui("Error: No recent orders found.")
            return None
    else:
        log_to_ui(f"Error: {response.status_code}")
        return None


# Nomatin App
# def get_zip_code_from_address(address):
#     endpoint = f'https://nominatim.openstreetmap.org/search?q={address}&format=json'
    
#     try:
#         response = requests.get(endpoint)
#         if response.status_code == 200:
#             data = response.json()
#             if data and len(data):
#                 zip_code = data[0].get('address').get('postcode')
#                 return zip_code
#             else:
#                 return None
#         else:
#             return None
#     except requests.exceptions.RequestException as e:
#         print(f"Error: {e}")
#         return None

# OpenCage (only free trial after 1 month)
# def get_zip_code_from_address(address):
#     api_key = "d4b7584bafdf480ea1b89d64fcec4d42"
#     geocoder = OpenCageGeocode(api_key)
#     try:
#         results = geocoder.geocode(address)
#         if results and len(results):
#             components = results[0]['components']
#             zip_code = components.get('postcode')
#             return zip_code
#         else:
#             return None
#     except Exception as e:
#         print(f"Error: {e}")
#         return None


def get_zip_code_from_address(address):
    # Initialize Nominatim geocoder
    print("inside_geo",address)
    find_address = ""
    geolocator = Nominatim(user_agent="my_geocoder")
    segments = address.split(',')
    # Loop through the segments, removing the first segment each time
    for i in range(len(segments)):
        # Create a new sentence from the remaining segments
        new_address = ', '.join(segment.strip() for segment in segments[i:])
        # Geocode the address
        location = geolocator.geocode(new_address)
        print("In Loop")

        # Check if location was found
        if location:
            # Extract ZIP code if available
            if 'postcode' in location.raw['address']:
                find_address = location.raw['address']['postcode']
                print("Zip Code Get", find_address)
                break
            else:
                find_address = None
        else:
            print(f"Could not find the location for '{address}'.")
            find_address = None
    
    if find_address == None:
        return None
    else: 
        return find_address


def send_order_to_pos(url, json_response, sku_id, product_ids, variation_ids, quantities, full_address):
    items = []
    combo_product_variations = []
    combo_variation_ids = []  # For storing unique IDs for combo product variations

    address = full_address
    get_zip = get_zip_code_from_address(address)
    print("Address", address)
    if get_zip:
        print("Zip Code:", get_zip)
    else:
        print("Cant Get Zip")

    # Process items
    for prod_id, var_id, qty in zip(product_ids, variation_ids, quantities):
        item = {
            "quantity": qty,
            "variation_id": var_id,
            "product_id": prod_id
        }
        items.append(item)

    # Process combo product variations
    for prod_id, var_id, qty in zip(product_ids, variation_ids, quantities):
        # Generate a unique ID for each combo product variation
        combo_variation_id = f"{sku_id}_{prod_id}_{var_id}"
        if combo_variation_id not in combo_variation_ids:
            combo_variation_ids.append(combo_variation_id)
            combo_variation = {
                "count": qty,
                "id": combo_variation_id,
                "product_id": prod_id,
                "variation_id": var_id
            }
            combo_product_variations.append(combo_variation)
        else:
            # If the combo variation ID already exists, find its index and update the count
            index = combo_variation_ids.index(combo_variation_id)
            combo_product_variations[index]["count"] += qty

    payload = {
        "order": {
            "shop_id": SHOP_ID,
            "page_id": PAGE_ID,
            "shipping_address": json_response,
            "items": items,
            "activated_combo_products": [
                {
                    "combo_product_id": sku_id,
                    "combo_product_info": {
                        "combo_product_variations": combo_product_variations
                    }
                }
            ]
        }
    }

    #log_to_ui(f"Payload: {json.dumps(payload, indent=2)}")

    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + ACCESS_TOKEN
    }
    
    response = requests.put(url, headers=headers, data=json.dumps(payload))
    return response.status_code


def toggle_tag(conversation_id):
    url = f"https://pancake.ph/api/v1/pages/{PAGE_ID}/conversations/{conversation_id}/toggle_tag?access_token={ACCESS_TOKEN}"
    payload = {'tag_id': ID_IT_TAG, 'value': '1'}
    headers = {}
    response = requests.request("POST", url, headers=headers, data=payload)
    if response.status_code == 200:
        log_to_ui("Order successfully Tagged.")
        return "Successful"
    else:
        log_to_ui(f"Error occurred while toggling tag. Status code: {response.status_code}")
        return "Error"


def is_within_window(inserted_at):
    try:
        inserted_at_local = datetime.datetime.strptime(inserted_at, "%Y-%m-%dT%H:%M:%S") + datetime.timedelta(hours=8)
        now_local = datetime.datetime.now() + datetime.timedelta(hours=8)
        cutoff_yesterday = datetime.datetime.combine((now_local - datetime.timedelta(days=1)).date(), CUTOFF_TIME)
        cutoff_today = datetime.datetime.combine(now_local.date(), CUTOFF_TIME)
        return cutoff_yesterday <= inserted_at_local <= cutoff_today
    except ValueError:
        log_to_ui(f"Error: Invalid inserted_at format: {inserted_at}")
        return False


def prepare_log_file():
    global log_file_name  # Ensure global scope for log_file_name
    current_date = datetime.datetime.now().strftime("%m_%d")
    log_file_name = f"terminal_logs_{PAGE_NAME}_{current_date}.txt"
    return log_file_name


def get_sku_id(sku_name):
    sku_id = None
    product_ids = []
    variation_ids = []
    quantities = []

    try:
        # Split the SKU name by '='
        items_and_total_cost = sku_name.rsplit('=', 1)
        if len(items_and_total_cost) != 2:
            log_to_ui("Invalid SKU format.")
            return None, None, None, None
        
        items = items_and_total_cost[0].split('+')
        total_cost = items_and_total_cost[1]
        
        # Extract quantities and item names
        for item in items:
            qty = ''
            item_name = ''
            for char in item:
                if char.isdigit():
                    qty += char
                else:
                    item_name += char

            if not qty.isdigit():
                log_to_ui(f"Invalid quantity format for item: {item}")
                continue
            
            qty = int(qty)
            quantities.append(qty)
            #log_to_ui(f"Item: {item_name}, Quantity: {qty}")
        
        # URL for fetching SKU ID, product IDs, and variation IDs based on the SKU name
        combo_url = f"https://pos.pages.fm/api/v1/shops/{SHOP_ID}/combo_products"
        combo_params = {
            "search": sku_name.lower(),
            "access_token": ACCESS_TOKEN
        }

        # Fetching combo product information
        combo_response = requests.get(combo_url, params=combo_params)
        if combo_response.status_code == 200:
            combo_data = combo_response.json()
            for combo_product in combo_data.get('data', []):
                if combo_product.get('name').lower() == sku_name.lower():
                    sku_id = combo_product.get('id')
                    #log_to_ui(f"SKU ID: {sku_id}")
                    for variation in combo_product.get('variations', []):
                        product_id = variation.get('product_id')
                        variation_id = variation.get('id')
                        product_ids.append(product_id)
                        variation_ids.append(variation_id)
                        #log_to_ui(f"Product ID: {product_id}, Variation ID: {variation_id}")
                    break
        else:
            log_to_ui(f"Error fetching combo product ID: {combo_response.status_code}")

    except IndexError as e:
        log_to_ui(f"IndexError: {e}")
    except KeyError as e:
        log_to_ui(f"KeyError: {e}")
    except Exception as e:
        log_to_ui(f"An unexpected error occurred: {e}")
    
    # Return the gathered information
    return sku_id, product_ids, variation_ids, quantities

def main():
    global PAGE_ID
    global log_file_name
    iteration_logs = []

    get_page_id(PAGE_NAME, ACCESS_TOKEN)
    if PAGE_ID is None:
        log_to_ui("Error: Unable to retrieve page ID. Exiting.")
        return

    get_page_settings()
    exported_tag_id = get_exported_tag_id(SHOP_ID, ACCESS_TOKEN)
    encoded_tag_id = get_encoded_tag_id(SHOP_ID, ACCESS_TOKEN)
    log_to_ui(f"ID of 'EXPORTED' tag: {exported_tag_id}")
    log_to_ui(f"ID of 'ENCODED' tag: {encoded_tag_id}")

    if ID_IT_TAG is None or ORDER_IT_TAG is None or SHOP_ID is None:
        log_to_ui("Error: Unable to retrieve settings. Exiting.")
        return

    while True:
        try:
            current_date = datetime.datetime.now()
            start_date = current_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = current_date.replace(hour=23, minute=59, second=59, microsecond=999999)
            START_DATE = int(start_date.timestamp())
            END_DATE = int(end_date.timestamp())

            log_file_name = prepare_log_file()

            log_to_ui("Checking conversations...")
            conversations = get_conversations(START_DATE, END_DATE)
            iteration_logs.clear()
            if conversations:
                for conversation in conversations:
                    customer = conversation['customers'][0]
                    conversation_id = conversation['id']
                    customer_id = customer['id']

                    latest_order_info = get_latest_order_info(conversation_id, customer_id)
                    if latest_order_info:
                        latest_order_tags = latest_order_info.get('tags')
                        latest_order_inserted_at = latest_order_info.get('inserted_at')

                        if latest_order_tags and (exported_tag_id in latest_order_tags or encoded_tag_id in latest_order_tags):
                            log_to_ui("Skipping conversation as tags EXPORTED or ENCODED are present.")
                            continue

                        if not is_within_window(latest_order_inserted_at):
                            log_to_ui("Inserted_at date is not within the desired window. Skipping conversation.")
                            continue

                        latest_order_id = latest_order_info.get('id')
                        send_order_url = f"https://pos.pages.fm/api/v1/shops/{SHOP_ID}/orders/{latest_order_id}?access_token={ACCESS_TOKEN}"

                        messages = get_messages(conversation_id, customer_id)
                        if messages:
                            log_to_ui(f"Conversation ID: {conversation_id}")
                            log_to_ui(f"Customer: {customer['name']}")
                            log_to_ui("Messages:")
                            original_messages = []
                            latest_sku = None
                            latest_sku_id = None
                            latest_product_id = None
                            latest_variation_id = None
                            latest_quantity = None

                            for message in messages:
                                if 'from' in message and 'id' in message['from']:
                                    if message['from']['id'] == customer['fb_id']:
                                        original_message = message.get('original_message', '(No original message)')
                                        original_messages.append(original_message)
                                        log_to_ui(f"- {original_message}")
                                    elif message['from']['id'] == PAGE_ID:  # Check if the message is from the page
                                        # Extract SKU using '=' as identifier
                                        message_text = message.get('original_message', '')
                                        sku = get_last_sku(message_text)
                                        if sku:
                                            #log_to_ui(f"SKU: {sku}")
                                            # Fetch SKU ID, product ID, variation ID, and quantity
                                            sku_id, product_id, variation_id, quantity = get_sku_id(sku)
                                            if sku_id and product_id and variation_id and quantity:
                                                log_to_ui(f"SKU ID: {sku_id}, Product ID: {product_id}, Variation ID: {variation_id}, Quantity: {quantity}")
                                                latest_sku = sku
                                                latest_sku_id = sku_id
                                                latest_product_id = product_id
                                                latest_variation_id = variation_id
                                                latest_quantity = quantity
                                            else:
                                                log_to_ui("Failed to retrieve SKU ID, product ID, variation ID, or quantity.")
                            if not latest_sku:
                                log_to_ui("No valid SKU found in the message.")

                            if latest_sku and original_messages:
                                openai_response = send_to_openai(" ".join(original_messages))
                                log_to_ui(f"OpenAI Response: {openai_response}")
                                if openai_response:
                                    try:
                                        openai_response_json = json.loads(openai_response)
                                        json_response = {
                                            "country_code": "63",
                                            "province_id": openai_response_json.get("province_id", ""),
                                            "district_id": openai_response_json.get("district_id", ""),
                                            "commune_id": openai_response_json.get("commune_id", ""),
                                            "address": openai_response_json.get("address", "")
                                        }

                                        full_address = openai_response_json.get("full_address", "")

                                        pos_response_code = send_order_to_pos(
                                            send_order_url, json_response, latest_sku_id, 
                                            latest_product_id, latest_variation_id, latest_quantity, full_address
                                        )

                                        if pos_response_code == 200:
                                            log_to_ui("Order successfully sent to POS.")
                                            toggle_tag_response_code = toggle_tag(conversation_id)
                                        else:
                                            log_to_ui(f"Error occurred while sending order to POS. Response code: {pos_response_code}")
                                    except json.decoder.JSONDecodeError as e:
                                        log_to_ui(f"Error decoding JSON response: {e}")
                                else:
                                    log_to_ui("Empty response from OpenAI.")
                            else:
                                log_to_ui("Missing SKU ID, product ID, variation ID, or quantity. Skipping OpenAI request and order sending.")
                    else:
                        log_to_ui("Error: Unable to fetch latest order info.")
                        pass
                    iteration_logs.append("Placeholder log for conversation processing")

            log_to_ui("======================")
            log_to_ui(f"Iteration end timestamp: {datetime.datetime.now()}")
            log_to_ui(f"Logs for this iteration have been saved to: {log_file_name}")
            log_to_ui("Waiting for 5 minutes before checking conversations again...")
            time.sleep(300)
        except Exception as e:
            log_to_ui(f"An error occurred: {e}")
            continue


def start_script():
    access_token = access_token_entry.get()
    page_name = page_name_entry.get()

    if access_token and page_name:
        # Replace the global variables with the values from the UI input fields
        global ACCESS_TOKEN, PAGE_NAME
        ACCESS_TOKEN = access_token
        PAGE_NAME = page_name

        # Start the script in a separate thread
        start_thread = threading.Thread(target=continuous_script, daemon=True)
        start_thread.start()
    else:
        messagebox.showerror("Error", "Please provide both ACCESS_TOKEN and PAGE_NAME.")


def continuous_script():
    while True:
        # Execute the main script function
        main()


def start_script():
    access_token = access_token_entry.get()
    page_name = page_name_entry.get()

    if access_token and page_name:
        # Replace the global variables with the values from the UI input fields
        global ACCESS_TOKEN, PAGE_NAME
        ACCESS_TOKEN = access_token
        PAGE_NAME = page_name

        root.title(f"Encoder Bot PMC - {page_name}")
        
        # Start the script in a separate thread
        start_thread = threading.Thread(target=continuous_script, daemon=True)
        start_thread.start()
    else:
        messagebox.showerror("Error", "Please provide both ACCESS_TOKEN and PAGE_NAME.")


root = tk.Tk()
root.title(f"Encoder Bot PMC")

# Access Token Label and Entry
access_token_label = tk.Label(root, text="ACCESS_TOKEN:")
access_token_label.grid(row=0, column=0, padx=5, pady=5, sticky="e")

access_token_entry = tk.Entry(root)
access_token_entry.grid(row=0, column=1, padx=5, pady=5, sticky="we")


# Page Name Label and Entry
page_name_label = tk.Label(root, text="PAGE_NAME:")
page_name_label.grid(row=1, column=0, padx=5, pady=5, sticky="e")

page_name_entry = tk.Entry(root)
page_name_entry.grid(row=1, column=1, padx=5, pady=5, sticky="we")

# Start Button
start_button = tk.Button(root, text="Start Script", command=start_script)
start_button.grid(row=2, column=0, columnspan=2, padx=5, pady=5, sticky="we")

# Text Widget to display terminal prints
output_text_widget = scrolledtext.ScrolledText(root, width=50, height=20, wrap=tk.WORD)
output_text_widget.grid(row=3, column=0, columnspan=2, padx=5, pady=5, sticky="we")

root.mainloop()
