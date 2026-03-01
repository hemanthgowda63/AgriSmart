from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
import requests
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.conf import settings

import os
from django.core.files.storage import default_storage
from django.conf import settings

from django.contrib.auth.decorators import login_required

import base64
import json

# Optional: use official SDK if available (more reliable)
try:
    import google.generativeai as genai
    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False


def _call_gemini(prompt, api_key=None):
    """Call Gemini API (text only) and return generated text. Returns (text, error_message)."""
    api_key = api_key or getattr(settings, "GEMINI_API_KEY", None)
    if not api_key:
        return None, "Gemini API key is not configured."

    quota_msg = "Gemini quota exceeded. Wait a minute and try again, or check usage: https://ai.dev/rate-limit"

    # Prefer official SDK
    if _GENAI_AVAILABLE:
        try:
            genai.configure(api_key=api_key)
            sdk_last_error = None
            for model_name in ("gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro", "gemini-2.0-flash"):
                try:
                    model = genai.GenerativeModel(model_name)
                    response = model.generate_content(prompt)
                    if response and response.text:
                        return response.text.strip(), None
                except Exception as e:
                    err_msg = str(e).lower()
                    if "404" in err_msg or "not found" in err_msg:
                        continue
                    if "429" in err_msg or "quota" in err_msg:
                        sdk_last_error = quota_msg
                        continue
                    return None, f"Gemini error: {e}"
            if sdk_last_error:
                return None, sdk_last_error
        except Exception as e:
            return None, f"Gemini SDK error: {e}"

    # Fallback: REST API with detailed error
    last_error = None
    for model in ("gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro", "gemini-2.0-flash"):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        try:
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            response = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=30,
            )
            if response.status_code == 200:
                data = response.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[0].get("text", "").strip(), None
            else:
                try:
                    err_body = response.json()
                    msg = err_body.get("error", {}).get("message", response.text)
                except Exception:
                    msg = response.text
                last_error = quota_msg if response.status_code == 429 else f"API {response.status_code}: {msg}"
                if response.status_code in (404, 429):
                    continue
                break
        except requests.exceptions.RequestException as e:
            last_error = str(e)
            break
    return None, last_error or "Gemini API request failed."


def _call_gemini_vision(prompt, image_base64, mime_type="image/jpeg", api_key=None):
    """Send image + prompt to Gemini and return generated text. Returns (text, error_message)."""
    api_key = api_key or getattr(settings, "GEMINI_API_KEY", None)
    if not api_key:
        return None, "Gemini API key is not configured."

    quota_msg = "Gemini quota exceeded. Wait a minute and try again, or check usage: https://ai.dev/rate-limit"

    # Prefer official SDK with image (inline_data format)
    if _GENAI_AVAILABLE:
        try:
            genai.configure(api_key=api_key)
            sdk_last_error = None
            for model_name in ("gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro", "gemini-2.0-flash"):
                try:
                    model = genai.GenerativeModel(model_name)
                    image_part = {"inline_data": {"mime_type": mime_type, "data": image_base64}}
                    response = model.generate_content([image_part, prompt])
                    if response and response.text:
                        return response.text.strip(), None
                except Exception as e:
                    err_msg = str(e).lower()
                    if "404" in err_msg or "not found" in err_msg:
                        continue
                    if "429" in err_msg or "quota" in err_msg:
                        sdk_last_error = quota_msg
                        continue
                    return None, f"Gemini vision error: {e}"
            if sdk_last_error:
                return None, sdk_last_error
        except Exception as e:
            return None, f"Gemini SDK error: {e}"

    # Fallback: REST with inline_data
    last_error = None
    for model in ("gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro", "gemini-2.0-flash"):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        try:
            payload = {
                "contents": [{
                    "parts": [
                        {"inline_data": {"mime_type": mime_type, "data": image_base64}},
                        {"text": prompt}
                    ]
                }]
            }
            response = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=60,
            )
            if response.status_code == 200:
                data = response.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[0].get("text", "").strip(), None
            else:
                try:
                    err_body = response.json()
                    msg = err_body.get("error", {}).get("message", response.text)
                except Exception:
                    msg = response.text
                last_error = quota_msg if response.status_code == 429 else f"API {response.status_code}: {msg}"
                if response.status_code in (404, 429):
                    continue
                break
        except requests.exceptions.RequestException as e:
            last_error = str(e)
            break
    return None, last_error or "Gemini vision request failed."


def _call_openai(prompt, api_key=None):
    """Call OpenAI Chat API (text only). Returns (text, error_message)."""
    api_key = api_key or getattr(settings, "OPENAI_API_KEY", None)
    if not api_key:
        return None, "OpenAI API key is not configured."
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1024,
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            data = response.json()
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()
            if content:
                return content, None
        err_body = response.json() if response.content else {}
        msg = err_body.get("error", {}).get("message", response.text)
        return None, f"OpenAI API {response.status_code}: {msg}"
    except requests.exceptions.RequestException as e:
        return None, str(e)


def _call_openai_vision(prompt, image_base64, mime_type="image/jpeg", api_key=None):
    """Send image + prompt to OpenAI (vision). Returns (text, error_message)."""
    api_key = api_key or getattr(settings, "OPENAI_API_KEY", None)
    if not api_key:
        return None, "OpenAI API key is not configured."
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    image_url = f"data:{mime_type};base64,{image_base64}"
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            }
        ],
        "max_tokens": 1024,
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        if response.status_code == 200:
            data = response.json()
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()
            if content:
                return content, None
        err_body = response.json() if response.content else {}
        msg = err_body.get("error", {}).get("message", response.text)
        return None, f"OpenAI API {response.status_code}: {msg}"
    except requests.exceptions.RequestException as e:
        return None, str(e)


from django.shortcuts import render



def signup_view(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')

        # basic validation
        if not email or not password:
            return render(request, 'signup.html', {'error': 'Email and password are required'})

        username = email  # we use email as username

        # check if user already exists
        if User.objects.filter(username=username).exists():
            return render(request, 'signup.html', {'error': 'User already exists. Please login.'})

        # create user
        user = User.objects.create_user(username=username, email=email, password=password)

        # log user in immediately
        login(request, user)

        # go to dashboard
        return redirect('dashboard')

    # GET request → just show the page
    return render(request, 'signup.html')



def login_view(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')

        user = authenticate(request, username=email, password=password)
        if user is not None:
            login(request, user)
            return redirect('dashboard')
        else:
            return render(request, 'login.html', {'error': 'Invalid email or password'})

    return render(request, 'login.html')


def logout_view(request):
    logout(request)
    return redirect('login')


def dashboard_view(request):
    if not request.user.is_authenticated:
        return redirect('login')
    return render(request, 'dashboard.html')


# placeholder views for now, so links don't break:
import requests
from django.conf import settings

def weather_view(request):
    if not request.user.is_authenticated:
        return redirect('login')

    weather_data = None

    if request.method == 'POST':
        city = request.POST.get('city')
        api_key = settings.OPENWEATHER_API_KEY
        url = f"https://api.openweathermap.org/data/2.5/forecast?q={city}&appid={api_key}&units=metric"

        r = requests.get(url)
        if r.status_code == 200:
            data = r.json()
            current = data['list'][0]          # now
            forecast = data['list'][1:6]       # next few time slots

            weather_data = {
                'city': city,
                'current': current,
                'forecast': forecast,
            }
        else:
            weather_data = {'error': 'City not found or API error'}

    return render(request, 'weather.html', {'weather_data': weather_data})

from django.contrib.auth.decorators import login_required
from .models import Post

@login_required
def community_view(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        content = request.POST.get('content')
        if title and content:
            Post.objects.create(user=request.user, title=title, content=content)
            return redirect('community')

    posts = Post.objects.all().order_by('-created_at')
    return render(request, 'community.html', {'posts': posts})


@login_required
def scan_view(request):
    result = None
    uploaded_image_url = None
    error = None

    if request.method == 'POST' and request.FILES.get('image'):
        image_file = request.FILES['image']

        # 1) Save image for preview
        path = default_storage.save('temp/' + image_file.name, image_file)
        full_path = os.path.join(settings.MEDIA_ROOT, path)
        uploaded_image_url = settings.MEDIA_URL + path

        try:
            # 2) Read file and convert to base64
            with open(full_path, "rb") as f:
                img_bytes = f.read()
                img_b64 = base64.b64encode(img_bytes).decode("ascii")

            mime_type = getattr(image_file, "content_type", None) or "image/jpeg"
            if mime_type not in ("image/jpeg", "image/png", "image/webp", "image/gif"):
                mime_type = "image/jpeg"

            url = settings.PLANTID_API_URL

            headers = {
                "Content-Type": "application/json",
                "Api-Key": settings.PLANTID_API_KEY,
            }

            payload = {
                "images": [img_b64],
                "health": "only",   # we only want health/disease info
            }

            response = requests.post(url, headers=headers, json=payload)

            # ✅ Treat 200 and 201 as success
            if response.status_code in (200, 201):
                data = response.json()
                result_block = data.get("result", {})

                is_healthy_info = result_block.get("is_healthy", {})
                is_healthy = is_healthy_info.get("binary", None)

                disease_block = result_block.get("disease", {})
                suggestions = disease_block.get("suggestions", [])

                if is_healthy is True:
                    # Plant appears healthy
                    prob = float(is_healthy_info.get("probability", 0)) * 100
                    result = {
                        "disease": "Plant appears healthy",
                        "confidence": round(prob, 2),
                        "remedies": None,
                    }
                elif suggestions:
                    # pick highest probability suggestion
                    top = max(suggestions, key=lambda s: s.get("probability", 0))
                    disease_name = top.get("name", "Unknown disease")
                    probability = float(top.get("probability", 0)) * 100
                    result = {
                        "disease": disease_name,
                        "confidence": round(probability, 2),
                        "remedies": None,
                    }
                else:
                    result = {
                        "disease": "Unknown",
                        "confidence": 0,
                        "remedies": None,
                    }

                # Send image to OpenAI for remedies & precautions
                vision_prompt = (
                    "You are an agricultural expert. Look at this plant/leaf image carefully. "
                    "(1) Identify any disease or health issue; if the plant looks healthy, say so briefly. "
                    "(2) Give clear remedies and precautions for Indian farmers in simple language. "
                    "Use bullet points or short numbered steps. No chemical brand names. "
                    "Keep it practical and easy to follow."
                )
                ai_text, ai_err = _call_openai_vision(vision_prompt, img_b64, mime_type)
                if ai_text:
                    result["remedies"] = ai_text
                elif ai_err and not result.get("remedies"):
                    result["remedies"] = f"(Could not load AI advice: {ai_err})"

                if not is_healthy and not suggestions:
                    error = "No disease suggestions from scanner. See AI analysis above if available."
            else:
                # Real HTTP error
                try:
                    err_json = response.json()
                    err_msg = err_json.get("error", {}).get("message", response.text)
                except Exception:
                    err_msg = response.text

                error = f"Plant.id API error ({response.status_code}): {err_msg}"

        except Exception as e:
            error = f"Error processing image or calling API: {e}"

    return render(request, 'scan.html', {
        "result": result,
        "uploaded_image_url": uploaded_image_url,
        "error": error,
    })




@login_required
def market_view(request):
    # Demo market data (Indian mandi-style prices). Replace with API/DB later.
    market_data = [
        {"commodity": "Rice", "market": "Delhi", "state": "Delhi", "price": 2850, "unit": "quintal", "trend": "up"},
        {"commodity": "Rice", "market": "Mumbai", "state": "Maharashtra", "price": 2920, "unit": "quintal", "trend": "down"},
        {"commodity": "Wheat", "market": "Indore", "state": "Madhya Pradesh", "price": 2350, "unit": "quintal", "trend": "up"},
        {"commodity": "Wheat", "market": "Kota", "state": "Rajasthan", "price": 2280, "unit": "quintal", "trend": "same"},
        {"commodity": "Tomato", "market": "Bangalore", "state": "Karnataka", "price": 42, "unit": "kg", "trend": "down"},
        {"commodity": "Tomato", "market": "Hyderabad", "state": "Telangana", "price": 38, "unit": "kg", "trend": "up"},
        {"commodity": "Onion", "market": "Nashik", "state": "Maharashtra", "price": 28, "unit": "kg", "trend": "same"},
        {"commodity": "Onion", "market": "Pune", "state": "Maharashtra", "price": 30, "unit": "kg", "trend": "up"},
        {"commodity": "Potato", "market": "Agra", "state": "Uttar Pradesh", "price": 18, "unit": "kg", "trend": "down"},
        {"commodity": "Cotton", "market": "Yavatmal", "state": "Maharashtra", "price": 6200, "unit": "quintal", "trend": "up"},
        {"commodity": "Soybean", "market": "Ujjain", "state": "Madhya Pradesh", "price": 3850, "unit": "quintal", "trend": "same"},
        {"commodity": "Maize", "market": "Nizamabad", "state": "Telangana", "price": 1950, "unit": "quintal", "trend": "down"},
    ]
    return render(request, 'market.html', {"market_data": market_data})


@csrf_exempt
@login_required
def chatbot_view(request):
    if request.method == 'POST':
        user_msg = request.POST.get('message', '').strip()
        if not user_msg:
            return JsonResponse({'reply': "Please type or speak a question first."})

        prompt = (
            "You are a helpful farmer assistant AI. "
            "Give short, simple guidance for Indian farmers. "
            "Use easy language and avoid chemical product brand names. "
            f"User question: {user_msg}"
        )
        try:
            text, err = _call_openai(prompt)
            bot_reply = text if text else (err or "OpenAI API is unavailable. Please check your API key and try again.")
        except Exception as e:
            bot_reply = f"Error talking to AI: {e}"

        return JsonResponse({'reply': bot_reply})

    return render(request, 'chatbot.html')

from django.contrib.auth.decorators import login_required

