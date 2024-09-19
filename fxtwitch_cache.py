# fxtwitch by RoyRiv3r

import os
import logging
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, HTMLResponse, PlainTextResponse
import requests
from urllib.parse import urlencode
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Initialize FastAPI app
app = FastAPI()

# Configure Logging
LOGGING_ENABLED = os.getenv('LOGGING_ENABLED', 'false').lower() == 'true'

logger = logging.getLogger("app_logger")
if LOGGING_ENABLED:
  logging.basicConfig(
      level=logging.INFO,
      format="%(asctime)s - %(levelname)s - %(message)s",
  )
  logger.setLevel(logging.INFO)
  logger.info("🔍 Logging is enabled.")
else:
  logging.basicConfig(level=logging.WARNING)  # Suppress logs if disabled

# Twitch credentials from environment variables
TWITCH_CLIENT_ID = os.getenv('TWITCH_CLIENT_ID')
TWITCH_CLIENT_SECRET = os.getenv('TWITCH_CLIENT_SECRET')

# Constants
GITHUB_REDIRECT_URL = 'https://github.com/RoyRiv3r/RoyRiv3r'
TINYURL_API = 'https://tinyurl.com/api-create.php'

def fetch_twitch_access_token() -> dict:
  """
  Fetches Twitch OAuth access token.
  """
  logger.info("🔑 Fetching Twitch access token from API.")
  url = 'https://id.twitch.tv/oauth2/token'
  params = {
      'client_id': TWITCH_CLIENT_ID,
      'client_secret': TWITCH_CLIENT_SECRET,
      'grant_type': 'client_credentials'
  }

  response = requests.post(url, params=params)

  if response.status_code != 200:
      logger.error(f"❌ Failed to get access token: {response.text}")
      raise Exception(f"Failed to get access token: {response.text}")

  data = response.json()
  logger.info("✅ Twitch access token obtained successfully.")
  return data

def fetch_clip_info_sync(clip_id: str) -> dict:
  """
  Fetches clip information from Twitch using their GraphQL API.
  """
  logger.info(f"🔍 Fetching clip info for clip_id: {clip_id}")
  access_token_data = fetch_twitch_access_token()
  access_token = access_token_data['access_token']
  url = 'https://gql.twitch.tv/gql'
  headers = {
      'Client-ID': 'kimne78kx3ncx6brgo4mv6wki5h1ko',  # Static Client-ID used by Twitch web
      'Authorization': f'Bearer {access_token}',
      'Content-Type': 'application/json',
  }

  payload = [
      {
          "operationName": "VideoPlayerStreamInfoOverlayClip",
          "variables": {"slug": clip_id},
          "extensions": {
              "persistedQuery": {
                  "version": 1,
                  "sha256Hash": "fcefd8b2081e39d16cbdc94bc82142df01b143bb296f0043262c44c37dbd1f63"
              }
          }
      },
      {
          "operationName": "VideoAccessToken_Clip",
          "variables": {"platform": "web", "slug": clip_id},
          "extensions": {
              "persistedQuery": {
                  "version": 1,
                  "sha256Hash": "6fd3af2b22989506269b9ac02dd87eb4a6688392d67d94e41a6886f1e9f5c00f"
              }
          }
      }
  ]

  response = requests.post(url, headers=headers, json=payload)

  if response.status_code != 200:
      logger.error(f"❌ Failed to get clip info: {response.text}")
      raise Exception(f"Failed to get clip info: {response.text}")

  response_data = response.json()

  # Parse clip information
  try:
      clip_data = response_data[0]['data']['clip']
      access_data = response_data[1]['data']['clip']['playbackAccessToken']
      video_qualities = response_data[1]['data']['clip']['videoQualities']
  except (IndexError, KeyError, TypeError) as e:
      logger.error(f"❌ Unexpected response structure: {str(e)}")
      raise Exception(f"Unexpected response structure: {str(e)}")

  signature = access_data['signature']
  token = access_data['value']

  # Select the first available video quality
  video_url = video_qualities[0]['sourceURL']
  final_video_url = f"{video_url}?sig={signature}&token={requests.utils.quote(token)}"

  clip_info = {
      'broadcaster_name': clip_data['broadcaster']['displayName'],
      'title': clip_data['title'],
      'url': f"https://clips.twitch.tv/{clip_data['slug']}",
      'view_count': clip_data['viewCount'],
      'creator_name': clip_data['broadcaster']['login'],
      'thumbnail_url': f"https://clips-media-assets2.twitch.tv/{clip_data['slug']}-preview-480x272.jpg",
      'video_url': final_video_url
  }

  logger.info(f"✅ Clip info retrieved for clip_id: {clip_id}")
  return clip_info

def fetch_shortened_url_sync(url: str) -> str:
  """
  Shortens a given URL using the TinyURL API.
  """

  logger.info(f"🔗 Shortening URL: {url}")
  params = {'url': url}
  response = requests.get(TINYURL_API, params=params)

  if response.status_code != 200:
      logger.error('❌ Failed to shorten URL')
      raise Exception('Failed to shorten URL')

  shortened = response.text.strip()
  logger.info(f"✅ URL shortened to: {shortened}")
  return shortened

async def get_twitch_access_token() -> str:
  """
  Asynchronous wrapper to get Twitch access token.
  """
  token_data = fetch_twitch_access_token()
  return token_data['access_token']

async def get_clip_info(clip_id: str) -> dict:
  """
  Asynchronous wrapper to get clip information.
  """
  clip_info = fetch_clip_info_sync(clip_id)
  return clip_info

async def shorten_url(url: str) -> str:
  """
  Asynchronous wrapper to shorten URLs.
  """
  return fetch_shortened_url_sync(url)

@app.get("/", response_class=RedirectResponse)
def root():
  """
  Redirect the root URL to the specified GitHub repository.
  """
  logger.info("🏠 Root endpoint accessed; redirecting to GitHub repository.")
  return RedirectResponse(url=GITHUB_REDIRECT_URL, status_code=301)

@app.get("/clip/{clip_id}")
async def handle_clip(clip_id: str, request: Request):
    """
    Handle Twitch clip requests by processing the clip ID, including metadata for bots 
    and redirecting for regular users.
    """
    logger.info(f"🎥 Handling clip request for clip_id: {clip_id}")
    try:
        clip_info = await get_clip_info(clip_id)
        video_url = clip_info['video_url']
        logger.info(f"🔗 Clip info retrieved for clip_id: {clip_id}")

        # Check if the request is from a bot
        user_agent = request.headers.get("user-agent", "").lower()
        bot_agents = ["bot", "crawler", "spider", "slurp", "facebookexternalhit", "whatsapp"]
        is_bot = any(agent in user_agent for agent in bot_agents)

        if is_bot:
            # For bots, return HTML with metadata
            html_content = f"""
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="theme-color" content="#6441a5">
                <meta property="og:title" content="{clip_info['broadcaster_name']} - {clip_info['title']}">
                <meta property="og:type" content="video">
                <meta property="og:site_name" content="👁️ Views: {clip_info['view_count']} | {clip_info['creator_name']}">
                <meta property="og:url" content="{clip_info['url']}">
                <meta property="og:video" content="{video_url}">
                <meta property="og:video:secure_url" content="{video_url}">
                <meta property="og:video:type" content="video/mp4">
                <meta property="og:image" content="{clip_info['thumbnail_url']}">
            </head>
            <body>
                <p>This page contains metadata for bots.</p>
            </body>
            </html>
            """
            logger.info(f"🤖 Responding with metadata HTML for bot (clip_id: {clip_id})")
            return HTMLResponse(content=html_content, status_code=200)
        else:
            # For regular users, perform a 301 redirect
            logger.info(f"🔀 Redirecting to video URL for clip_id: {clip_id}")
            return RedirectResponse(url=video_url, status_code=301)

    except Exception as e:
        logger.error(f"❌ Error handling clip_id {clip_id}: {str(e)}")
        return PlainTextResponse(content=f"Error: {str(e)}", status_code=500)


@app.middleware("http")
async def catch_not_found(request: Request, call_next):
  """
  Middleware to handle 404 Not Found for undefined routes.
  """
  response = await call_next(request)
  if response.status_code == 404:
      logger.warning(f"🚫 404 Not Found: {request.url}")
      return PlainTextResponse(content="Not Found", status_code=404)
  return response

# To run the application, use the following command:
# uvicorn fxtwitch:app --host 0.0.0.0 --port 8000