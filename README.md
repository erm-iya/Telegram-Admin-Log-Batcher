# **Optimized Telegram Deleted Message Scraper**

This is an advanced Python script that scans a Telegram group/channel's admin log to find out which messages were deleted, who sent them, and which admin deleted them.

It is heavily optimized to run quickly and avoid Telegram's rate limits by using batch processing for users, caching user data, and implementing an adaptive rate limiter. So you can have your deleted telegram messages in your storage!

Fun Fact: You can also import them by converting to .txt and compress to .zip file, just like sharing Whatsapp messages to a Telegram group!

## **Requirements**

* Python 3.7+  
* The telethon and nest\_asyncio libraries

## **Installation**

1. Make sure you have Python installed.  
2. Install the required libraries using pip:  
   pip install telethon nest\_asyncio

## **How to Use**

This script is fully interactive and will prompt you for all needed information. You do **not** need to edit the .py file.

### **Step 1: Get API Credentials**

1. Log in to your Telegram account at [my.telegram.org](https://my.telegram.org).  
2. Go to "API development tools" and create a new application.  
3. You will be given your api\_id and api\_hash. Keep these ready.

### **Step 2: Run the Script**

1. Open your terminal or command prompt.  
2. Navigate to the directory where telegram\_scraper.py is saved.  
3. Run the script:  
   python telegram\_scraper.py

4. The script will immediately ask for your api\_id and api\_hash.  
5. If it's your first time running it, it will ask for your **phone number**, then the **login code** Telegram sends you, and finally your **2FA password** if you have one.  
6. After logging in, it will ask for the **target channel/group ID or username** (e.g., @mychannel or \-100123456789).  
   * **Note:** To get deleted messages, you **must** be an admin in that channel with the right to view the admin log.  
7. The script will start processing and will print its progress.  
8. When finished, it will save a JSON report file (e.g., deleted\_messages\_optimized\_-100123...json) in the same directory.
