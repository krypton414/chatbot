import React, { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import { Send, Globe, Bot, User, Loader2 } from 'lucide-react';

function App() {
  const [messages, setMessages] = useState([
    {
      id: 1,
      text: "Hello! I'm Anoni, your AI assistant. I can help you with general questions, FAQs, and analyze websites. What would you like to know?\n",
      sender: 'bot',
      timestamp: new Date()
    }
  ]);
  const [inputMessage, setInputMessage] = useState('');
  const [websiteUrl, setWebsiteUrl] = useState('https://anonivate.com/');
  const [isLoading, setIsLoading] = useState(false);
  const [isWebsiteMode, setIsWebsiteMode] = useState(false);
  const [currentWebsite, setCurrentWebsite] = useState('');
  const [sessionId, setSessionId] = useState('');
  const [userInfo, setUserInfo] = useState(null);
  const [showOnboarding, setShowOnboarding] = useState(false);

  const messagesEndRef = useRef(null);

  // API base URL - use localhost for development, production URL for deployment
  const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Get or create user information from localStorage
  const getUserInfo = () => {
    const stored = localStorage.getItem('chatbot_user_info');
    return stored ? JSON.parse(stored) : null;
  };

  // Save user information to localStorage
  const saveUserInfo = (info) => {
    localStorage.setItem('chatbot_user_info', JSON.stringify(info));
    setUserInfo(info);
  };

  // Generate or retrieve existing session ID from localStorage
  const getOrCreateSessionId = () => {
    let existingSessionId = localStorage.getItem('chatbot_session_id');
    
    if (!existingSessionId) {
      existingSessionId = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
      localStorage.setItem('chatbot_session_id', existingSessionId);
    }
    
    return existingSessionId;
  };

  // Get website URL from URL parameters and initialize session
  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const websiteUrlParam = urlParams.get('website_url');
    
    // 🔑 Initialize persistent session ID from localStorage
    setSessionId(getOrCreateSessionId());
    
    // Check if user info exists
    const existingUserInfo = getUserInfo();
    if (existingUserInfo) {
      setUserInfo(existingUserInfo);
    } else {
      // Show onboarding for new users
      setShowOnboarding(true);
    }
    
    if (websiteUrlParam) {
      setCurrentWebsite(websiteUrlParam);
      setWebsiteUrl(websiteUrlParam);
      setIsWebsiteMode(true);
      // Update the welcome message to show which website is being analyzed
      const existingUserInfo = getUserInfo();
      if (existingUserInfo) {
        setMessages(prev => [
          {
            ...prev[0],
            text: `Hello ${existingUserInfo.name}! I'm ${existingUserInfo.assistantName}, your AI assistant. I can help you with general questions and provide information about the website: ${websiteUrlParam}. What would you like to know?\n`
          }
        ]);
      } else {
        setMessages(prev => [
          {
            ...prev[0],
            text: `Hello! I'm Anoni, your AI assistant. I can help you with general questions and provide information about the website: ${websiteUrlParam}. What would you like to know?\n`
          }
        ]);
      }
    }
  }, []);

  const sendMessage = async () => {
    if (!inputMessage.trim()) return;

    const userMessage = {
      id: Date.now(),
      text: inputMessage,
      sender: 'user',
      timestamp: new Date()
    };

    setMessages(prev => [...prev, userMessage]);
    setInputMessage('');
    setIsLoading(true);

    try {
      const requestData = { 
        message: inputMessage,
        session_id: sessionId,
        user_name: userInfo?.name || null,
        user_email: userInfo?.email || null,
        assistant_name: userInfo?.assistantName || null
      };
      
      // Add website_url as query parameter if available
      const params = {};
      if (currentWebsite) {
        params.website_url = currentWebsite;
      }
      
      const response = await axios.post(`${API_BASE_URL}/chat`, requestData, { params });

      const botMessage = {
        id: Date.now() + 1,
        text: response.data.response,
        sender: 'bot',
        timestamp: new Date()
      };



      setMessages(prev => [...prev, botMessage]);
    } catch (error) {
      console.error('Error sending message:', error);
      const errorMessage = {
        id: Date.now() + 1,
        text: "Sorry, I encountered an error. Please try again.",
        sender: 'bot',
        timestamp: new Date()
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const toggleWebsiteMode = () => {
    setIsWebsiteMode(!isWebsiteMode);
    if (!isWebsiteMode) {
      setMessages(prev => [...prev, {
        id: Date.now(),
        text: "Website analysis mode enabled!",
        sender: 'bot',
        timestamp: new Date()
      }]);
    }
  };

  const clearMemory = async () => {
    try {
      await axios.delete(`${API_BASE_URL}/memory/${sessionId}`);
      // Clear local storage too
      localStorage.removeItem('chatbot_session_id');
      localStorage.removeItem('chatbot_user_info');
      // Generate new session ID
      const newSessionId = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
      setSessionId(newSessionId);
      localStorage.setItem('chatbot_session_id', newSessionId);
      
      // Reset user info and show onboarding
      setUserInfo(null);
      setShowOnboarding(true);
      
      // Add a message about memory being cleared
      setMessages(prev => [...prev, {
        id: Date.now(),
        text: "🧠 Memory cleared! Starting fresh conversation.",
        sender: 'bot',
        timestamp: new Date()
      }]);
    } catch (error) {
      console.error('Error clearing memory:', error);
    }
  };

  // Onboarding Form Component
  const OnboardingForm = () => {
    const [formData, setFormData] = useState({
      name: '',
      email: '',
      assistantName: 'Anoni'
    });

    const handleSubmit = (e) => {
      e.preventDefault();
      if (formData.name.trim() && formData.email.trim()) {
        saveUserInfo(formData);
        setShowOnboarding(false);
        
        // Add welcome message with user's name
        const welcomeMessage = {
          id: Date.now(),
          text: `Hello ${formData.name}! I'm ${formData.assistantName}, your AI assistant. I can help you with general questions and provide information about the website: ${currentWebsite || 'various topics'}. What would you like to know?`,
          sender: 'bot',
          timestamp: new Date()
        };
        setMessages([welcomeMessage]);
      }
    };

    return (
      <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
        <div className="bg-white rounded-lg p-6 max-w-md w-full mx-4">
          <h2 className="text-2xl font-bold text-gray-900 mb-4">Welcome! Let's Get Started</h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Your Name *
              </label>
              <input
                type="text"
                required
                value={formData.name}
                onChange={(e) => setFormData({...formData, name: e.target.value})}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                placeholder="Enter your name"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Email Address *
              </label>
              <input
                type="email"
                required
                value={formData.email}
                onChange={(e) => setFormData({...formData, email: e.target.value})}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                placeholder="Enter your email"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                What should I call you?
              </label>
              <input
                type="text"
                value={formData.assistantName}
                onChange={(e) => setFormData({...formData, assistantName: e.target.value})}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                placeholder="e.g., Anoni, Assistant, etc."
              />
            </div>
            <button
              type="submit"
              className="w-full bg-blue-600 text-white py-2 px-4 rounded-lg hover:bg-blue-700 transition-colors"
            >
              Get Started
            </button>
          </form>
        </div>
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* Onboarding Form */}
      {showOnboarding && <OnboardingForm />}
      
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-4xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <Bot className="h-8 w-8 text-blue-600" />
              <h1 className="text-2xl font-bold text-gray-900">AI Chatbot</h1>
              {currentWebsite && (
                <div className="text-sm text-blue-600 bg-blue-100 px-3 py-1 rounded-full">
                  Analyzing: {currentWebsite}
                </div>
              )}
            </div>
            <div className="flex items-center space-x-2">
              {/* Remove Mode Selector */}
              <button
                onClick={toggleWebsiteMode}
                className={`flex items-center space-x-2 px-4 py-2 rounded-lg transition-colors ${
                  isWebsiteMode
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                <Globe className="h-4 w-4" />
                <span className="text-sm font-medium">
                  {isWebsiteMode ? 'Website Mode' : 'General Mode'}
                </span>
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Website URL Input */}
      {isWebsiteMode && (
        <div className="bg-white border-b border-gray-200 px-4 py-3">
          <div className="max-w-4xl mx-auto">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Website URL to analyze:
            </label>
            <input
              type="url"
              value={websiteUrl}
              disabled
              className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-gray-100 text-gray-500 cursor-not-allowed"
            />
          </div>
        </div>
      )}

      {/* Memory Management */}
      <div className="bg-blue-50 border-b border-blue-200 px-4 py-3">
        <div className="max-w-4xl mx-auto">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <span className="text-sm font-medium text-blue-800">🧠 AI Memory Active</span>
              {userInfo && (
                <span className="text-xs text-green-600 bg-green-100 px-2 py-1 rounded-full">
                  {userInfo.name}
                </span>
              )}
              <span className="text-xs text-blue-600 bg-blue-100 px-2 py-1 rounded-full">
                Session: {sessionId ? sessionId.substring(0, 20) + '...' : 'Loading...'}
              </span>
            </div>
            <div className="flex items-center space-x-2">
              <button
                onClick={clearMemory}
                className="text-xs text-red-600 hover:text-red-800 px-2 py-1 rounded border border-red-200 hover:bg-red-100 transition-colors"
              >
                Clear Memory
              </button>
            </div>
          </div>

        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4">
        <div className="max-w-4xl mx-auto space-y-4">
          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex ${message.sender === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-xs lg:max-w-md px-4 py-3 rounded-lg ${
                  message.sender === 'user'
                    ? 'bg-blue-600 text-white'
                    : 'bg-white text-gray-900 border border-gray-200'
                }`}
              >
                <div className="flex items-start space-x-2">
                  {message.sender === 'user' ? (
                    <User className="h-5 w-5 mt-0.5 flex-shrink-0" />
                  ) : (
                    <Bot className="h-5 w-5 mt-0.5 flex-shrink-0 text-blue-600" />
                  )}
                  <div className="flex-1">
                    <div 
                      className="text-sm chat-html-content"
                      dangerouslySetInnerHTML={{ __html: message.text }}
                    />
                    <p className="text-xs opacity-70 mt-1">
                      {message.timestamp.toLocaleTimeString()}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          ))}
          {isLoading && (
            <div className="flex justify-start">
              <div className="bg-white text-gray-900 border border-gray-200 rounded-lg px-4 py-3">
                <div className="flex items-center space-x-2">
                  <Loader2 className="h-5 w-5 animate-spin text-blue-600" />
                  <span className="text-sm">Thinking...</span>
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input */}
      <div className="bg-white border-t border-gray-200 p-4">
        <div className="max-w-4xl mx-auto">
          <div className="flex space-x-3">
            <div className="flex-1">
              <textarea
                value={inputMessage}
                onChange={(e) => setInputMessage(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder="Type your message here..."
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
                rows="1"
                style={{ minHeight: '44px', maxHeight: '120px' }}
              />
            </div>
            <button
              onClick={sendMessage}
              disabled={!inputMessage.trim() || isLoading}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center space-x-2"
            >
              <Send className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
