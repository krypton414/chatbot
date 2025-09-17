from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List
import os
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup
import openai
import json
import time
from urllib.parse import urljoin, urlparse

load_dotenv()

app = FastAPI(title="Chatbot API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# FAQ data
faq_data = {
    "What is this chatbot?": "This is an AI-powered chatbot that can answer questions about websites and general FAQs.",
    "How does it work?": "The chatbot uses OpenAI's GPT model to understand and respond to your questions. It can also analyze website content to provide specific answers.",
    "Can it analyze websites?": "Yes! You can provide a website URL and the chatbot will analyze its content to provide specific answers about that specific website.",
    "What technologies are used?": "This chatbot uses React for the frontend, FastAPI for the backend, and OpenAI's GPT model for responses."
}

# Conversation Memory System
conversation_memory = {}  # Store conversation history by session_id

def get_conversation_context(session_id: str, max_messages: int = 10) -> str:
    """Get conversation context for memory"""
    if session_id not in conversation_memory:
        return ""
    
    # Get last few messages for context
    recent_messages = conversation_memory[session_id][-max_messages:]
    context = "\n".join([f"User: {msg['user']}\nAssistant: {msg['assistant']}" for msg in recent_messages])
    return context

def add_to_memory(session_id: str, user_message: str, assistant_response: str):
    """Add conversation to memory"""
    if session_id not in conversation_memory:
        conversation_memory[session_id] = []
    
    conversation_memory[session_id].append({
        'user': user_message,
        'assistant': assistant_response,
        'timestamp': time.time()
    })
    
    # Keep only last 20 messages to prevent memory overflow
    if len(conversation_memory[session_id]) > 20:
        conversation_memory[session_id] = conversation_memory[session_id][-20:]

def create_memory_summary(session_id: str) -> str:
    """Create a summary of conversation context for AI"""
    if session_id not in conversation_memory or len(conversation_memory[session_id]) == 0:
        return ""
    
    # Get conversation context
    context = get_conversation_context(session_id, 5)
    
    if not context:
        return ""
    
    # Create a brief summary
    summary = f"Previous conversation context:\n{context}\n\nUse this context to provide more relevant and contextual responses."
    return summary

def convert_markdown_to_html(text: str) -> str:
    """Convert markdown-style responses to proper HTML"""
    if not text:
        return text
    
    # First, handle headers that end with : (like "**Services:**")
    lines = text.split('\n')
    processed_lines = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Convert headers like "**Services:**" to h2 tags
        if line.startswith('**') and line.endswith('**:'):
            header_text = line.replace('**', '').replace(':', '')
            processed_lines.append(f'<h2><strong>{header_text}</strong></h2>')
        # Convert other bold text like "**UI/UX:**" to strong tags
        elif line.startswith('**') and line.endswith('**'):
            bold_text = line.replace('**', '')
            processed_lines.append(f'<strong>{bold_text}</strong>')
        # Convert bullet points to numbered lists
        elif line.startswith('- ') or line.startswith('* '):
            content = line[2:].strip()
            # Remove any remaining ** from the content
            content = content.replace('**', '<strong>').replace('**', '</strong>')
            processed_lines.append(f'<p>• {content}</p>')
        else:
            # Regular paragraph - clean up any ** and * in the text
            cleaned_line = line
            # Handle **text** pattern properly
            import re
            cleaned_line = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', cleaned_line)
            # Handle *text* pattern for emphasis
            cleaned_line = re.sub(r'\*(.*?)\*', r'<em>\1</em>', cleaned_line)
            processed_lines.append(f'<p>{cleaned_line}</p>')
    
    result = '\n'.join(processed_lines)
    
    # Clean up any double p tags
    result = result.replace('<p><p>', '<p>')
    result = result.replace('</p></p>', '</p>')
    
    # Clean up any p tags that contain h2 tags
    result = result.replace('<p><h2>', '<h2>')
    result = result.replace('</h2></p>', '</h2>')
    
    return result

class ChatMessage(BaseModel):
    message: str
    website_url: Optional[str] = None
    mode: Optional[str] = "basic"  # 'design', 'basic', or 'development'
    session_id: Optional[str] = None  # For conversation memory
    user_name: Optional[str] = None  # User's name from onboarding
    user_email: Optional[str] = None  # User's email from onboarding
    assistant_name: Optional[str] = None  # Assistant's preferred name

class ChatResponse(BaseModel):
    response: str
    sources: Optional[List[str]] = None
    memory_summary: Optional[str] = None  # Summary of conversation context

def scrape_website(url: str) -> str:
    """Scrape website content"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
        
        # Get text content
        text = soup.get_text()
        
        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = ' '.join(chunk for chunk in chunks if chunk)
        
        return text[:8000]  # Limit content length
    except Exception as e:
        return f"Error scraping website: {str(e)}"

def scrape_multiple_pages(start_url: str, max_pages: int = 5) -> str:
    """Crawl and scrape up to max_pages internal pages starting from start_url."""
    visited = set()
    to_visit = [start_url]
    all_text = ""
    domain = urlparse(start_url).netloc
    while to_visit and len(visited) < max_pages:
        url = to_visit.pop(0)
        if url in visited:
            continue
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            # Add delay to prevent rate limiting
            time.sleep(1)
            
            soup = BeautifulSoup(response.content, 'html.parser')
            for script in soup(["script", "style"]):
                script.decompose()
            text = soup.get_text()
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            page_text = ' '.join(chunk for chunk in chunks if chunk)
            all_text += page_text[:4000]  # Limit per page
            visited.add(url)
            # Find internal links
            for link in soup.find_all('a', href=True):
                href = link['href']
                joined = urljoin(url, href)
                parsed = urlparse(joined)
                if parsed.netloc == domain and joined not in visited and joined not in to_visit:
                    to_visit.append(joined)
        except Exception:
            continue
    return all_text[:16000]  # Limit total content

def detect_mode(message: str) -> str:
    design_keywords = ["design", "ui", "ux", "color", "layout", "branding", "typography", "visual", "logo", "font", "palette", "style"]
    dev_keywords = ["code", "api", "react", "backend", "frontend", "deploy", "database", "server", "javascript", "python", "html", "css", "function", "bug", "error", "component"]
    msg = message.lower()
    if any(word in msg for word in design_keywords):
        return "design"
    if any(word in msg for word in dev_keywords):
        return "development"
    return "basic"

async def get_openai_response(system_prompt: str, user_message: str, memory_context: str = "") -> str:
    """Get response from OpenAI API with memory context"""
    try:
        # Include memory context in system prompt if available
        if memory_context:
            enhanced_system_prompt = f"{system_prompt}\n\n{memory_context}"
        else:
            enhanced_system_prompt = system_prompt
        
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": enhanced_system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=0.7,
            max_tokens=800
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error getting AI response: {str(e)}"

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(chat_message: ChatMessage, website_url: str = Query(None, description="Website URL to analyze")):
    try:
        user_message = chat_message.message
        mode = detect_mode(chat_message.message)

        # Custom greeting response for 'How are you?' and similar
        greeting_patterns = [
            r"^how are you[\?!. ]*$",
            r"^how are you doing[\?!. ]*$",
            r"^how r u[\?!. ]*$",
            r"^how do you feel[\?!. ]*$",
            r"^what's up[\?!. ]*$",
            r"^sup[\?!. ]*$",
            r"^are you okay[\?!. ]*$",
            r"^are you fine[\?!. ]*$",
            r"^are you good[\?!. ]*$",
        ]
        import re
        if any(re.match(pat, user_message.strip().lower()) for pat in greeting_patterns):
            chatgpt_style_greeting = (
                "<h2><strong>How am I?</strong></h2>"
                "<p>I don't have feelings, but I'm ready and working fine — here to help! 🙂 How are <em>you</em> doing?</p>"
            )
            add_to_memory(chat_message.session_id or "default_session", user_message, chatgpt_style_greeting)
            return ChatResponse(response=chatgpt_style_greeting)
        
        # Generate session ID if not provided
        session_id = chat_message.session_id or "default_session"
        
        # Get memory context for this session
        memory_context = create_memory_summary(session_id)
        
        # Prepare user context for AI
        user_context = ""
        if chat_message.user_name:
            user_context += f"User's name: {chat_message.user_name}. "
        if chat_message.user_email:
            user_context += f"User's email: {chat_message.user_email}. "
        if chat_message.assistant_name:
            user_context += f"Assistant should call itself: {chat_message.assistant_name}. "
        
        # If no user context, provide default
        if not user_context:
            user_context = "No user information provided. "
        
        # Debug: Print user context
        print(f"DEBUG: User context: '{user_context}'")
        print(f"DEBUG: User name: {chat_message.user_name}")
        print(f"DEBUG: User email: {chat_message.user_email}")
        print(f"DEBUG: Assistant name: {chat_message.assistant_name}")
        
        # Enhance user message with context for better AI understanding
        enhanced_user_message = f"{user_message}"
        if chat_message.user_name:
            enhanced_user_message += f" [IMPORTANT: The user's name is {chat_message.user_name}. When they ask about their name, tell them their name is {chat_message.user_name}.]"
        if chat_message.user_email:
            enhanced_user_message += f" [IMPORTANT: The user's email is {chat_message.user_email}. When they ask about their email, tell them their email is {chat_message.user_email}.]"
        
        # Use website_url from query parameter if provided, otherwise use message body
        target_website = website_url if website_url else chat_message.website_url
        
        # If website URL is provided, analyze the website FIRST (PRIORITY)
        if target_website:
            website_content = scrape_multiple_pages(target_website, max_pages=5)
            # Always use OpenAI to answer, even if website_content is empty or scraping fails
            system_prompt = f"""🤖 You are a helpful AI assistant. The user is asking about a website ({target_website}).

👤 **USER INFORMATION - USE THIS INFORMATION:**
{user_context}

💡 **CRITICAL INSTRUCTIONS - YOU MUST FOLLOW THESE:**
1. The user's name is: {chat_message.user_name or 'not provided'}
2. The user's email is: {chat_message.user_email or 'not provided'}
3. When the user asks 'what is my name?' or 'tell me my name', you MUST respond with their actual name: {chat_message.user_name or 'not provided'}
4. When the user asks 'what is my email?' or 'tell me my email', you MUST respond with their actual email: {chat_message.user_email or 'not provided'}
5. NEVER say you don't have access to this information - you DO have it above

📋 **CRITICAL FORMATTING RULES - YOU MUST FOLLOW THESE EXACTLY:**
• NEVER use markdown syntax like ** or * or bullet points
• NEVER use bullet points (•) or asterisks (*) for lists
• ALWAYS use proper HTML tags ONLY
• ALWAYS start with <h2><strong>Main Heading</strong></h2>
• ALWAYS wrap paragraphs in <p> tags with proper spacing
• ALWAYS use numbered lists (1. 2. 3.) wrapped in <p> tags
• ALWAYS use <em> tags for emphasis on important words
• ALWAYS use <strong> tags for key terms and concepts
• ALWAYS add <br><br> between sections for proper spacing
• NEVER skip HTML tags - they are REQUIRED

💡 **INSTRUCTIONS:**
If you can answer the user's question using the website content below, do so. If not, answer in your own words using your general knowledge, just like ChatGPT. Be helpful, friendly, and conversational.

🌐 **WEBSITE CONTENT TO ANALYZE:**
{website_content[:1000]}...

Example format:
<<<<<<< HEAD
<h2><strong>Response Title</strong></h2>
<p>Your response paragraph here.</p>
<p>1. <strong>First point</strong> - explanation</p>
<p>2. <strong>Second point</strong> - explanation</p>

User's question: {chat_message.message}"""
                
                response = await get_openai_response(fallback_prompt, enhanced_user_message, memory_context)
                
                # Add to memory
                add_to_memory(session_id, user_message, response)
                
                # Convert any remaining markdown to HTML
                response = convert_markdown_to_html(response)
                
                # IMPROVEMENT: Add a clear fallback message before the ChatGPT answer
                response = "<p><em>I couldn't find this information on the website, but here is what I know:</em></p><br>" + response
                return ChatResponse(
                    response=response,
                    memory_summary=memory_context
                )
            
            # Check if the question is related to the website content
            # If it's a general knowledge question, fall back to AI
            general_questions = [
                "india", "state", "city", "country", "capital", "population", "weather", "history",
                "geography", "culture", "food", "language", "religion", "politics", "economy",
                "science", "technology", "art", "music", "literature", "sports", "health", "education",
                "date", "today", "time", "current", "now", "what day", "what time", "calendar",
                "year", "month", "day", "hour", "minute", "second", "clock", "schedule"
            ]
            
            is_general_question = any(keyword in user_message.lower() for keyword in general_questions)
            
            if is_general_question:
                # For general questions, use AI knowledge instead of website content
                if mode == "design":
                    system_prompt = f"""🎨 You are an expert UI/UX and branding consultant. 

👤 **USER INFORMATION - USE THIS INFORMATION:**
{user_context}

💡 **CRITICAL INSTRUCTIONS - YOU MUST FOLLOW THESE:**
1. The user's name is: {chat_message.user_name or 'not provided'}
2. The user's email is: {chat_message.user_email or 'not provided'}
3. When the user asks "what is my name?" or "tell me my name", you MUST respond with their actual name: {chat_message.user_name or 'not provided'}
4. When the user asks "what is my email?" or "tell me my email", you MUST respond with their actual email: {chat_message.user_email or 'not provided'}
5. NEVER say you don't have access to this information - you DO have it above

📋 **CRITICAL FORMATTING RULES - YOU MUST FOLLOW THESE EXACTLY:**
• NEVER use markdown syntax like ** or * or bullet points
• NEVER use bullet points (•) or asterisks (*) for lists
• ALWAYS use proper HTML tags ONLY
• ALWAYS start with <h2><strong>Main Heading</strong></h2>
• ALWAYS wrap paragraphs in <p> tags with proper spacing
• ALWAYS use numbered lists (1. 2. 3.) wrapped in <p> tags
• ALWAYS use <em> tags for emphasis on important words
• ALWAYS use <strong> tags for key terms and concepts
• ALWAYS add <br><br> between sections for proper spacing
• NEVER skip HTML tags - they are REQUIRED

💡 **INSTRUCTIONS:**
Answer design-related questions in detail. You MUST use HTML formatting as specified above. NEVER use markdown.

Example format:
<h2><strong>Design Answer Title</strong></h2>
<p>Your first paragraph here.</p>
<p>1. <strong>First design point</strong> - explanation</p>
<p>2. <strong>Second design point</strong> - explanation</p>
<p><em>Important design note</em> about the topic.</p>"""
                elif mode == "development":
                    system_prompt = f"""💻 You are a senior web developer and technical expert. 

👤 **USER INFORMATION:**
{user_context}

💡 **CRITICAL INSTRUCTIONS - YOU MUST FOLLOW THESE:**
1. The user's name is: {chat_message.user_name or 'not provided'}
2. The user's email is: {chat_message.user_email or 'not provided'}
3. When the user asks "what is my name?" or "tell me my name", you MUST respond with their actual name: {chat_message.user_name or 'not provided'}
4. When the user asks "what is my email?" or "tell me my email", you MUST respond with their actual email: {chat_message.user_email or 'not provided'}
5. NEVER say you don't have access to this information - you DO have it above

📋 **CRITICAL FORMATTING RULES - YOU MUST FOLLOW THESE EXACTLY:**
• NEVER use markdown syntax like ** or * or bullet points
• NEVER use bullet points (•) or asterisks (*) for lists
• ALWAYS use proper HTML tags ONLY
• ALWAYS start with <h2><strong>Main Heading</strong></h2>
• ALWAYS wrap paragraphs in <p> tags with proper spacing
• ALWAYS use numbered lists (1. 2. 3.) wrapped in <p> tags
• ALWAYS use <em> tags for emphasis on important words
• ALWAYS use <strong> tags for key terms and concepts
• ALWAYS add <br><br> between sections for proper spacing
• NEVER skip HTML tags - they are REQUIRED

💡 **INSTRUCTIONS:**
Answer development-related questions in detail. You MUST use HTML formatting as specified above. NEVER use markdown.

Example format:
<h2><strong>Development Answer Title</strong></h2>
<p>Your first paragraph here.</p>
<p>1. <strong>First development point</strong> - explanation</p>
<p>2. <strong>Second development point</strong> - explanation</p>
<p><em>Important development note</em> about the topic.</p>"""
                else:
                    system_prompt = f"""🤖 You are a helpful AI assistant. 

👤 **USER INFORMATION:**
{user_context}

💡 **CRITICAL INSTRUCTIONS - YOU MUST FOLLOW THESE:**
1. The user's name is: {chat_message.user_name or 'not provided'}
2. The user's email is: {chat_message.user_email or 'not provided'}
3. When the user asks "what is my name?" or "tell me my name", you MUST respond with their actual name: {chat_message.user_name or 'not provided'}
4. When the user asks "what is my email?" or "tell me my email", you MUST respond with their actual email: {chat_message.user_email or 'not provided'}
5. NEVER say you don't have access to this information - you DO have it above

📋 **CRITICAL FORMATTING RULES - YOU MUST FOLLOW THESE EXACTLY:**
• NEVER use markdown syntax like ** or * or bullet points
• NEVER use bullet points (•) or asterisks (*) for lists
• ALWAYS use proper HTML tags ONLY
• ALWAYS start with <h2><strong>Main Heading</strong></h2>
• ALWAYS wrap paragraphs in <p> tags with proper spacing
• ALWAYS use numbered lists (1. 2. 3.) wrapped in <p> tags
• ALWAYS use <em> tags for emphasis on important words
• ALWAYS use <strong> tags for key terms and concepts
• ALWAYS add <br><br> between sections for proper spacing
• NEVER skip HTML tags - they are REQUIRED

💡 **INSTRUCTIONS:**
Answer questions clearly and concisely. You MUST use HTML formatting as specified above. NEVER use markdown.

Example format:
<h2><strong>Your Answer Title</strong></h2>
<p>Your first paragraph here.</p>
=======
<h2><strong>Website/General Answer Title</strong></h2>
<p>Your answer paragraph here.</p>
>>>>>>> c854c2ec (Update: Improved ChatGPT-style fallback and greeting responses)
<p>1. <strong>First point</strong> - explanation</p>
<p>2. <strong>Second point</strong> - explanation</p>
<p><em>Important note</em> about the topic.</p>"""
            response = await get_openai_response(system_prompt, enhanced_user_message, memory_context)
            add_to_memory(session_id, user_message, response)
            response = convert_markdown_to_html(response)
            return ChatResponse(
                response=response,
                memory_summary=memory_context
            )
        
        # General conversation (this should happen before FAQ check)
        if mode == "design":
            system_prompt = f"""🎨 You are an expert UI/UX and branding consultant. 

👤 **USER INFORMATION:**
{user_context}

📋 **CRITICAL FORMATTING RULES - YOU MUST FOLLOW THESE EXACTLY:**
• NEVER use markdown syntax like ** or * or bullet points
• NEVER use bullet points (•) or asterisks (*) for lists
• ALWAYS use proper HTML tags ONLY
• ALWAYS start with <h2><strong>Main Heading</strong></h2>
• ALWAYS wrap paragraphs in <p> tags with proper spacing
• ALWAYS use numbered lists (1. 2. 3.) wrapped in <p> tags
• ALWAYS use <em> tags for emphasis on important words
• ALWAYS use <strong> tags for key terms and concepts
• ALWAYS add <br><br> between sections for proper spacing
• NEVER skip HTML tags - they are REQUIRED

💡 **INSTRUCTIONS:**
Answer design-related questions in detail. You MUST use HTML formatting as specified above. NEVER use markdown.

Example format:
<h2><strong>Design Answer Title</strong></h2>
<p>Your first paragraph here.</p>
<p>1. <strong>First design point</strong> - explanation</p>
<p>2. <strong>Second design point</strong> - explanation</p>
<p><em>Important design note</em> about the topic.</p>"""
        elif mode == "development":
            system_prompt = f"""💻 You are a senior web developer and technical expert. 

👤 **USER INFORMATION:**
{user_context}

📋 **CRITICAL FORMATTING RULES - YOU MUST FOLLOW THESE EXACTLY:**
• NEVER use markdown syntax like ** or * or bullet points
• NEVER use bullet points (•) or asterisks (*) for lists
• ALWAYS use proper HTML tags ONLY
• ALWAYS start with <h2><strong>Main Heading</strong></h2>
• ALWAYS wrap paragraphs in <p> tags with proper spacing
• ALWAYS use numbered lists (1. 2. 3.) wrapped in <p> tags
• ALWAYS use <em> tags for emphasis on important words
• ALWAYS use <strong> tags for key terms and concepts
• ALWAYS add <br><br> between sections for proper spacing
• NEVER skip HTML tags - they are REQUIRED

💡 **INSTRUCTIONS:**
Answer development-related questions in detail. You MUST use HTML formatting as specified above. NEVER use markdown.

Example format:
<h2><strong>Development Answer Title</strong></h2>
<p>Your first paragraph here.</p>
<p>1. <strong>First development point</strong> - explanation</p>
<p>2. <strong>Second development point</strong> - explanation</p>
<p><em>Important development note</em> about the topic.</p>"""
        else:
            system_prompt = f"""🤖 You are a helpful AI assistant. 

👤 **USER INFORMATION:**
{user_context}

📋 **CRITICAL FORMATTING RULES - YOU MUST FOLLOW THESE EXACTLY:**
• NEVER use markdown syntax like ** or * or bullet points
• NEVER use bullet points (•) or asterisks (*) for lists
• ALWAYS use HTML tags ONLY
• ALWAYS start with <h2><strong>Main Heading</strong></h2>
• ALWAYS wrap paragraphs in <p> tags with proper spacing
• ALWAYS use numbered lists (1. 2. 3.) wrapped in <p> tags
• ALWAYS use <em> tags for emphasis on important words
• ALWAYS use <strong> tags for key terms and concepts
• ALWAYS add <br><br> between sections for proper spacing
• NEVER skip HTML tags - they are REQUIRED

💡 **INSTRUCTIONS:**
Answer questions clearly and concisely. You MUST use HTML formatting as specified above. NEVER use markdown.

Example format:
<h2><strong>Your Answer Title</strong></h2>
<p>Your first paragraph here.</p>
<p>1. <strong>First point</strong> - explanation</p>
<p>2. <strong>Second point</strong> - explanation</p>
<p><em>Important note</em> about the topic.</p>"""
        
        response = await get_openai_response(system_prompt, enhanced_user_message, memory_context)
        
        # Add to memory
        add_to_memory(session_id, user_message, response)
        
        # Convert any remaining markdown to HTML
        response = convert_markdown_to_html(response)
        
        return ChatResponse(
            response=response,
            memory_summary=memory_context
        )
    
        # Only check FAQ as a last resort if no other response was generated
        for faq_question, faq_answer in faq_data.items():
            if any(word in user_message.lower() for word in faq_question.lower().split()):
                # Add FAQ response to memory
                add_to_memory(session_id, user_message, faq_answer)
                
                # Convert any remaining markdown to HTML
                faq_answer = convert_markdown_to_html(faq_answer)
                
                return ChatResponse(
                    response=faq_answer,
                    memory_summary=memory_context
                )
        
        # If we get here, provide a general AI response
        system_prompt = f"""🤖 You are a helpful AI assistant. 

👤 **USER INFORMATION - USE THIS INFORMATION:**
{user_context}

💡 **CRITICAL INSTRUCTIONS - YOU MUST FOLLOW THESE:**
1. The user's name is: {chat_message.user_name or 'not provided'}
2. The user's email is: {chat_message.user_email or 'not provided'}
3. When the user asks "what is my name?" or "tell me my name", you MUST respond with their actual name: {chat_message.user_name or 'not provided'}
4. When the user asks "what is my email?" or "tell me my email", you MUST respond with their actual email: {chat_message.user_email or 'not provided'}
5. NEVER say you don't have access to this information - you DO have it above

📋 **CRITICAL FORMATTING RULES - YOU MUST FOLLOW THESE EXACTLY:**
• NEVER use markdown syntax like ** or * or bullet points
• NEVER use bullet points (•) or asterisks (*) for lists
• ALWAYS use proper HTML tags ONLY
• ALWAYS start with <h2><strong>Main Heading</strong></h2>
• ALWAYS wrap paragraphs in <p> tags with proper spacing
• ALWAYS use numbered lists (1. 2. 3.) wrapped in <p> tags
• ALWAYS use <em> tags for emphasis on important words
• ALWAYS use <strong> tags for key terms and concepts
• ALWAYS add <br><br> between sections for proper spacing
• NEVER skip HTML tags - they are REQUIRED

💡 **INSTRUCTIONS:**
Answer questions clearly and concisely. You MUST use HTML formatting as specified above. NEVER use markdown.

Example format:
<h2><strong>Your Answer Title</strong></h2>
<p>Your first paragraph here.</p>
<p>1. <strong>First point</strong> - explanation</p>
<p>2. <strong>Second point</strong> - explanation</p>
<p><em>Important note</em> about the topic.</p>"""

        response = await get_openai_response(system_prompt, enhanced_user_message, memory_context)
        
        # Add to memory
        add_to_memory(session_id, user_message, response)
        
        # Convert any remaining markdown to HTML
        response = convert_markdown_to_html(response)
        
        return ChatResponse(
            response=response,
            memory_summary=memory_context
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing chat: {str(e)}")

@app.get("/health")
async def health_check():
    return {
        "status": "healthy", 
        "message": "Chatbot API is running",
        "website_url": os.getenv("WEBSITE_URL", "https://www.anonivate.com/")
    }

@app.get("/config")
async def get_config():
    return {
        "website_url": os.getenv("WEBSITE_URL", "https://www.anonivate.com/"),
        "has_website_content": True
    }

@app.get("/memory/{session_id}")
async def get_memory(session_id: str):
    """Get conversation memory for a specific session"""
    if session_id not in conversation_memory:
        return {"session_id": session_id, "messages": [], "count": 0}
    
    return {
        "session_id": session_id,
        "messages": conversation_memory[session_id],
        "count": len(conversation_memory[session_id])
    }

@app.delete("/memory/{session_id}")
async def clear_memory(session_id: str):
    """Clear conversation memory for a specific session"""
    if session_id in conversation_memory:
        del conversation_memory[session_id]
        return {"message": f"Memory cleared for session {session_id}"}
    return {"message": f"No memory found for session {session_id}"}

@app.get("/memory")
async def list_sessions():
    """List all active conversation sessions"""
    return {
        "active_sessions": list(conversation_memory.keys()),
        "total_sessions": len(conversation_memory)
    }

# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8000)
