import os
import logging
import asyncio
from dotenv import load_dotenv
from typing import Dict

import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

# Load .env if present
load_dotenv()

# Read tokens from environment (do NOT hardcode tokens)
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWM_API_KEY = os.getenv("OWM_API_KEY")

if not BOT_TOKEN:
    raise RuntimeError("Please set BOT_TOKEN environment variable")

# Set up logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- richer pre-planned data (replace previous mocks) ---
CROP_RECOMMENDATIONS: Dict[str, str] = {
    "wheat": "Urea 50kg/acre in two splits; use certified seeds; irrigate at tillering and before heading.",
    "rice": "DAP 40kg + Potash 20kg per acre; maintain flooded fields; use pest resistant seedlings.",
    "maize": "Apply NPK (20:20:20) at sowing and urea at 30 DAS; ensure good drainage and timely weeding.",
    "cotton": "Balanced NPK at sowing and top-dress nitrogen during vegetative growth; monitor boll formation.",
}

# Basic disease dictionary remains (can be expanded)
DISEASE_SYMPTOMS: Dict[str, str] = {
    "yellow leaves": "Could be nitrogen deficiency; test soil and consider urea.",
    "brown spots": "Possible fungal infection — consider fungicide and remove affected leaves.",
    "wilt": "Possible bacterial/fungal wilt or water stress; check root health and irrigation.",
}

# Pre-planned market data with short trend summary and mandi note
PREPLANNED_MARKET = {
    "wheat": {
        "current": "₹2,100 per quintal",
        "7day_trend": "down 2% (mild fall due to local harvest)",
        "mandi": "Nearby mandi: Raipur Mandi — good demand from flour mills.",
    },
    "urea": {
        "current": "₹8,500 per tonne",
        "7day_trend": "stable",
        "mandi": "Logistics delays expected; check bulk supply availability.",
    },
    "dap": {
        "current": "₹24,000 per tonne",
        "7day_trend": "up 1.5% (export demand)",
        "mandi": "Stocks limited — consider ordering early.",
    },
    "maize": {
        "current": "₹1,900 per quintal",
        "7day_trend": "up 3% (strong animal feed demand)",
        "mandi": "Higher demand in nearby feed plants.",
    },
}

# Add structured crop growth stages and short stage-wise tips
CROP_GROWTH = {
    "wheat": [
        ("Sowing", "Prepare fine seedbed; ensure recommended seed rate."),
        ("Tillering", "Apply first split of nitrogen; check for weeds."),
        ("Booting/Heading", "Apply second split of nitrogen; scout for pests."),
        ("Maturity", "Reduce irrigation and prepare for harvest."),
    ],
    "rice": [
        ("Nursery/Transplant", "Use healthy seedlings; transplant at 25-30 DAS."),
        ("Tillering", "Top dress nitrogen; maintain water levels."),
        ("Panicle Initiation", "Monitor for pests and apply recommended fungicide if necessary."),
        ("Maturity", "Drain field prior to harvest and dry properly."),
    ],
    "maize": [
        ("Germination", "Ensure moisture at seed depth; light irrigation if dry."),
        ("Vegetative", "Side-dress nitrogen at 30 DAS; control weeds."),
        ("Tasseling", "Watch for borers; timely irrigation."),
        ("Harvest", "Harvest when kernels are hard; sun-dry to required moisture."),
    ],
}

# Preplanned weather action notes (simple rules)
PREPLANNED_WEATHER_NOTES = {
    "hot_and_dry": "High temperature and low humidity — increase irrigation frequency and mulch soil.",
    "hot_and_humid": "High temp + humidity — risk of fungal diseases; consider preventive fungicide and avoid overhead irrigation at night.",
    "cold": "Low temperatures — protect young seedlings and avoid late irrigation that freezes.",
    "heavy_rain": "Expect waterlogging — ensure drainage and delay nitrogen application until fields dry.",
}

# Helper: create inline keyboard
def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("Weather", callback_data="cmd_weather")],
        [InlineKeyboardButton("Recommend crop", callback_data="cmd_recommend")],
        [InlineKeyboardButton("Market price", callback_data="cmd_price")],
        [InlineKeyboardButton("Report disease", callback_data="cmd_disease")],
    ]
    return InlineKeyboardMarkup(keyboard)


# --- Command Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = (
        f"🙏 Namaste {user.first_name}!\n\n"
        "🌾 *Welcome to Kissan Mitra Bot!*\n\n"
        "I am here to help:\n"
        "✔ Farmers with crop information\n"
        "✔ Shop owners with product updates\n"
        "✔ Weather, fertilizers, seeds & more\n\n"
        "Type /help to see all commands or use the buttons below."
    )
    await update.message.reply_markdown(message, reply_markup=main_menu_keyboard())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = (
        "📌 *Kissan Mitra Commands*\n\n"
        "/start - Start the bot\n"
        "/help - List of commands\n"
        "/farmer - Get help for farmers\n"
        "/shop - Help for shop owners\n\n"
        "*Quick actionable commands:*\n"
        "/weather <city> - Get weather\n"
        "/recommend <crop> - Fertilizer & seed tips\n"
        "/price <commodity> - Market price (sample)\n"
        "/disease <symptoms> - Get possible causes\n"
    )
    await update.message.reply_markdown(message)


async def farmer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = (
        "👨‍🌾 *Farmer Support*\n\n"
        "You can ask me:\n"
        "- Seeds information\n"
        "- Fertilizer suggestions\n"
        "- Weather updates\n"
        "- Crop disease help\n\n"
        "Example: *What fertilizer is best for wheat?*\n"
        "Try: `/recommend wheat`"
    )
    await update.message.reply_markdown(message)


async def shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = (
        "🛒 *Shop Owner Help*\n\n"
        "You can ask:\n"
        "- Product prices\n"
        "- Buyers nearby\n"
        "- Fertilizer/seed demand\n"
        "- Market trends\n\n"
        "Example: *What is the price of urea?*\n"
        "Try: `/price urea`"
    )
    await update.message.reply_markdown(message)


# --- Enhanced handlers + follow-up logic ---

async def weather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # if args provided use them, else ask follow-up
    if len(context.args) > 0:
        city = " ".join(context.args)
        await fetch_and_send_weather(update, context, city)
    else:
        await update.message.reply_text("Which city would you like weather for? (Example: Delhi)")
        context.user_data["awaiting"] = "weather"


async def recommend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) > 0:
        crop = " ".join(context.args).lower()
        await send_recommendation(update, context, crop)
    else:
        await update.message.reply_text("Which crop do you want recommendations for? (Example: wheat)")
        context.user_data["awaiting"] = "recommend"


async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) > 0:
        commodity = " ".join(context.args).lower()
        await send_price(update, context, commodity)
    else:
        await update.message.reply_text("Which commodity price would you like? (Example: urea)")
        context.user_data["awaiting"] = "price"


async def disease(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) > 0:
        symptoms = " ".join(context.args).lower()
        await send_disease_advice(update, context, symptoms)
    else:
        await update.message.reply_text(
            "Please describe the symptoms (e.g. 'yellow leaves' or 'brown spots'):"
        )
        context.user_data["awaiting"] = "disease"


# Helper to fetch and send weather (more fields + preplanned advice)
async def fetch_and_send_weather(update: Update, context: ContextTypes.DEFAULT_TYPE, city: str):
    if not OWM_API_KEY:
        await update.message.reply_text("Weather API key not configured. Set OWM_API_KEY in .env.")
        return

    url = "http://api.openweathermap.org/data/2.5/weather"
    params = {"q": city, "appid": OWM_API_KEY, "units": "metric"}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            if resp.status != 200:
                await update.message.reply_text(
                    f"Could not fetch weather for *{city.title()}*. Check the city name.",
                    parse_mode="Markdown",
                )
                return
            data = await resp.json()

    weather_main = data.get("weather", [{}])[0].get("description", "N/A").title()
    temp = data["main"].get("temp")
    feels = data["main"].get("feels_like")
    humidity = data["main"].get("humidity")
    pressure = data["main"].get("pressure")
    wind = data.get("wind", {}).get("speed")
    sunrise_ts = data.get("sys", {}).get("sunrise")
    sunset_ts = data.get("sys", {}).get("sunset")
    coord = data.get("coord", {})

    # Convert sunrise/sunset timestamps if present
    from datetime import datetime

    def fmt_ts(ts):
        if not ts:
            return "N/A"
        return datetime.fromtimestamp(ts).astimezone().strftime("%H:%M %Z")

    sunrise = fmt_ts(sunrise_ts)
    sunset = fmt_ts(sunset_ts)

    # Build weather advice using simple heuristics
    weather_key = None
    if temp is not None and humidity is not None:
        if temp >= 35 and humidity <= 40:
            weather_key = "hot_and_dry"
        elif temp >= 30 and humidity >= 60:
            weather_key = "hot_and_humid"
        elif temp <= 10:
            weather_key = "cold"

    # Compose message with preplanned suggestions and coordinates
    coord_text = f" (lat: {coord.get('lat')}, lon: {coord.get('lon')})" if coord else ""
    advice = PREPLANNED_WEATHER_NOTES.get(weather_key, "Normal conditions — follow regular schedule.")
    msg = (
        f"🌤️ Weather in *{city.title()}*{coord_text}\n\n"
        f"*Condition:* {weather_main}\n"
        f"*Temperature:* {temp} °C (feels like {feels} °C)\n"
        f"*Humidity:* {humidity}%\n"
        f"*Pressure:* {pressure} hPa\n"
        f"*Wind:* {wind} m/s\n"
        f"*Sunrise:* {sunrise}\n"
        f"*Sunset:* {sunset}\n\n"
        f"*Farmer tip:* {advice}\n"
        "_If you want local market impact on crops, try: /price <commodity>._"
    )
    await update.message.reply_markdown(msg)


# Helper for recommendations (includes growth stages + market hint)
async def send_recommendation(update: Update, context: ContextTypes.DEFAULT_TYPE, crop: str):
    crop = crop.lower()
    rec = CROP_RECOMMENDATIONS.get(crop)
    growth = CROP_GROWTH.get(crop)
    market = PREPLANNED_MARKET.get(crop)

    if rec:
        msg = f"🌾 *Recommendations for {crop.title()}*\n\n{rec}\n\n"
        if growth:
            msg += "*Growth stages & quick tips:*\n"
            for stage, tip in growth:
                msg += f"• *{stage}*: {tip}\n"
            msg += "\n"
        if market:
            msg += (
                f"*Market note:* Current {crop.title()} price: {market['current']} — 7d trend: {market['7day_trend']}\n"
            )
            msg += f"Nearby mandi note: {market['mandi']}\n\n"

        msg += "_If you want dosing details for a stage, ask: 'doses for <stage> of {0}'. (future)_".format(
            crop
        )
        await update.message.reply_markdown(msg)
    else:
        suggestions = ", ".join(sorted(CROP_RECOMMENDATIONS.keys()))
        await update.message.reply_markdown(
            f"Sorry, no data for *{crop.title()}*.\nTry these crops: {suggestions}"
        )


# Helper for price (returns preplanned market details + practical tip)
async def send_price(update: Update, context: ContextTypes.DEFAULT_TYPE, commodity: str):
    commodity = commodity.lower()
    # Try PREPLANNED_MARKET first
    p = PREPLANNED_MARKET.get(commodity)
    if p:
        msg = (
            f"💱 *{commodity.title()}* — Market snapshot\n\n"
            f"Current: {p['current']}\n"
            f"7-day trend: {p['7day_trend']}\n"
            f"Local mandi: {p['mandi']}\n\n"
            "_Practical tip:_ If trend is 'up', consider selling surplus; if 'down', store in proper conditions or look for forward buyers."
        )
        await update.message.reply_markdown(msg)
        return

    # Fallback to old simple mapping if present
    p_fallback = MARKET_PRICES.get(commodity) if "MARKET_PRICES" in globals() else None
    if p_fallback:
        await update.message.reply_markdown(f"💱 *{commodity.title()}* price (sample):\n{p_fallback}")
    else:
        await update.message.reply_markdown(
            f"No price data for *{commodity.title()}*. You can update PREPLANNED_MARKET or connect a live mandi API."
        )


# Helper for disease advice (more thorough)
async def send_disease_advice(update: Update, context: ContextTypes.DEFAULT_TYPE, symptoms: str):
    # Better matching (substring)
    for key, advice in DISEASE_SYMPTOMS.items():
        if key in symptoms:
            msg = (
                f"⚠️ *Possible cause:* {advice}\n\n"
                "Suggested actions:\n"
                "1. Inspect nearby plants for spread.\n"
                "2. Remove badly affected leaves and dispose safely.\n"
                "3. Test soil (pH/nutrient) if deficiency suspected.\n"
                "4. For unknown issues, upload a photo (future feature).\n"
            )
            await update.message.reply_markdown(msg)
            return

    # fallback
    await update.message.reply_markdown(
        "Could not match symptoms to a known issue. Please provide more details or send a photo."
    )


# Follow-up message handler to continue the conversation when the bot asked a question
async def follow_up_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    awaiting = context.user_data.get("awaiting")
    text = (update.message.text or "").strip()
    if not awaiting:
        # no awaiting action — ignore or treat as general chat
        return

    # Clear the awaiting flag
    context.user_data.pop("awaiting", None)

    if awaiting == "weather":
        await fetch_and_send_weather(update, context, text)
    elif awaiting == "recommend":
        await send_recommendation(update, context, text.lower())
    elif awaiting == "price":
        await send_price(update, context, text.lower())
    elif awaiting == "disease":
        await send_disease_advice(update, context, text.lower())
    else:
        await update.message.reply_text("Sorry, I didn't understand. Try /help for commands.")


# --- Callback for inline buttons ---
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "cmd_weather":
        await query.edit_message_text("Send /weather <city>\nExample: /weather Delhi")
    elif data == "cmd_recommend":
        await query.edit_message_text("Send /recommend <crop>\nExample: /recommend wheat")
    elif data == "cmd_price":
        await query.edit_message_text("Send /price <commodity>\nExample: /price urea")
    elif data == "cmd_disease":
        await query.edit_message_text("Send /disease <symptoms>\nExample: /disease brown spots")
    else:
        await query.edit_message_text("Unknown command.")


# --- Error handler ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    # Optionally notify the user in chat
    try:
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text("Sorry, an error occurred. The admin has been notified.")
    except Exception:
        pass


# --- Main app startup ---
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # core handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("farmer", farmer))
    app.add_handler(CommandHandler("shop", shop))

    # new feature handlers
    app.add_handler(CommandHandler("weather", weather))
    app.add_handler(CommandHandler("recommend", recommend))
    app.add_handler(CommandHandler("price", price))
    app.add_handler(CommandHandler("disease", disease))

    # follow-up handler for interactive flows (user replies after bot asks)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, follow_up_handler))

    # callbacks from inline keyboard
    app.add_handler(CallbackQueryHandler(callback_handler))

    # global error handler
    app.add_error_handler(error_handler)

    print("Kissan Mitra Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
