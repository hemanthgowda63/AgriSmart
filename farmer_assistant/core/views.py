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
import requests
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
                    }
                elif suggestions:
                    # pick highest probability suggestion
                    top = max(suggestions, key=lambda s: s.get("probability", 0))
                    disease_name = top.get("name", "Unknown disease")
                    probability = float(top.get("probability", 0)) * 100

                    result = {
                        "disease": disease_name,
                        "confidence": round(probability, 2),
                    }
                else:
                    error = "No disease suggestions returned. Try a clearer photo of the affected area."
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




def chatbot_view(request):
    if not request.user.is_authenticated:
        return redirect('login')
    return render(request, 'dashboard.html')  # temporary

def market_view(request):
    if not request.user.is_authenticated:
        return redirect('login')
    return render(request, 'dashboard.html')  # temporary


@csrf_exempt
@login_required
def chatbot_view(request):
    if request.method == 'POST':
        user_msg = request.POST.get('message', '').strip()
        if not user_msg:
            return JsonResponse({'reply': "Please type a question first."})

        api_key = settings.GEMINI_API_KEY
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"

        # Build prompt specifically for farming assistant
        prompt = (
            "You are a helpful farmer assistant AI. "
            "Give short, simple guidance for Indian farmers. "
            "Use easy language and avoid chemical product brand names. "
            f"User question: {user_msg}"
        )

        try:
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt}
                        ]
                    }
                ]
            }

            headers = {
                "Content-Type": "application/json"
            }

            response = requests.post(url, headers=headers, json=payload)
            if response.status_code == 200:
                data = response.json()
                # Gemini response path:
                # data["candidates"][0]["content"]["parts"][0]["text"]
                candidates = data.get("candidates", [])
                if candidates:
                    content = candidates[0].get("content", {})
                    parts = content.get("parts", [])
                    if parts:
                        bot_reply = parts[0].get("text", "I couldn't generate a reply.")
                    else:
                        bot_reply = "I couldn't understand the response from AI."
                else:
                    bot_reply = "No reply generated by AI. Please try again."
            else:
                bot_reply = f"Gemini API error: {response.status_code}"

        except Exception as e:
            bot_reply = f"Error talking to AI: {e}"

        return JsonResponse({'reply': bot_reply})

    # GET → show page
    return render(request, 'chatbot.html')

from django.contrib.auth.decorators import login_required

