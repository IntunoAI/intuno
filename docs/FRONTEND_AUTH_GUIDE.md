# Frontend Authentication Guide

This guide explains how the frontend should send authenticated requests to the API.

## Authentication Flow

1. **Login** to get a JWT access token
2. **Include the token** in the `Authorization` header for all protected endpoints
3. **Token expires** after 7 days (604,800 seconds)

## Step 1: Login

Send a POST request to `/auth/login` with email and password.

### Request

```javascript
// Using fetch
const response = await fetch('http://your-api-url/auth/login', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    email: 'user@example.com',
    password: 'your-password'
  })
});

const data = await response.json();
// Response: { access_token: "...", token_type: "bearer", expires_in: 604800 }
```

### Response Format

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 604800
}
```

**Store the `access_token`** in localStorage, sessionStorage, or your state management solution.

## Step 2: Authenticated Requests

For all protected endpoints, include the JWT token in the `Authorization` header.

### Important: Header Format

The header **must** be:
- Header name: `Authorization` (case-sensitive header name)
- Header value: `Bearer <token>` (with a space between "Bearer" and the token)

### Examples

#### JavaScript (fetch)

```javascript
const token = localStorage.getItem('access_token');

const response = await fetch('http://your-api-url/auth/me', {
  method: 'GET',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json',
  }
});

const userData = await response.json();
```

#### JavaScript (axios)

```javascript
import axios from 'axios';

const token = localStorage.getItem('access_token');

const response = await axios.get('http://your-api-url/auth/me', {
  headers: {
    'Authorization': `Bearer ${token}`
  }
});

const userData = response.data;
```

#### Axios with Interceptor (Recommended)

```javascript
import axios from 'axios';

// Create axios instance
const apiClient = axios.create({
  baseURL: 'http://your-api-url',
});

// Add token to all requests
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Use it
const response = await apiClient.get('/auth/me');
```

#### React Example

```javascript
import { useState, useEffect } from 'react';

function UserProfile() {
  const [user, setUser] = useState(null);
  const token = localStorage.getItem('access_token');

  useEffect(() => {
    fetch('http://your-api-url/auth/me', {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    })
      .then(res => res.json())
      .then(data => setUser(data))
      .catch(err => console.error('Error:', err));
  }, [token]);

  return <div>{user?.email}</div>;
}
```

#### cURL Example

```bash
curl -X GET "http://your-api-url/auth/me" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

## Common Endpoints

### Get Current User Info

```javascript
GET /auth/me
Headers: { Authorization: "Bearer <token>" }
```

### Create API Key

```javascript
POST /auth/api-keys
Headers: { Authorization: "Bearer <token>" }
Body: { "name": "My API Key" }
```

### List API Keys

```javascript
GET /auth/api-keys
Headers: { Authorization: "Bearer <token>" }
```

## Error Handling

### 401 Unauthorized

If you receive a 401 error, the token may be:
- Invalid
- Expired
- Missing

**Solution**: Redirect to login page and get a new token.

```javascript
if (response.status === 401) {
  // Token expired or invalid
  localStorage.removeItem('access_token');
  window.location.href = '/login';
}
```

### Complete Error Handling Example

```javascript
async function makeAuthenticatedRequest(url, options = {}) {
  const token = localStorage.getItem('access_token');
  
  if (!token) {
    throw new Error('No access token found. Please login.');
  }

  const response = await fetch(url, {
    ...options,
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });

  if (response.status === 401) {
    // Token expired or invalid
    localStorage.removeItem('access_token');
    window.location.href = '/login';
    throw new Error('Authentication failed');
  }

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Request failed');
  }

  return response.json();
}

// Usage
const userData = await makeAuthenticatedRequest('http://your-api-url/auth/me');
```

## Important Notes

1. **Header Name**: Use `Authorization` (not `authorization` or `AUTHORIZATION`)
2. **Header Value Format**: Must be exactly `Bearer <token>` with a space
3. **Token Storage**: Store tokens securely (consider httpOnly cookies for production)
4. **Token Expiration**: Tokens expire after 7 days - implement refresh logic if needed
5. **CORS**: Ensure your API allows requests from your frontend origin

## Testing with Postman/Insomnia

1. Set header name: `Authorization`
2. Set header value: `Bearer your-token-here`
3. Make request to protected endpoint

## Quick Reference

```javascript
// Login
POST /auth/login
Body: { email, password }

// Authenticated requests
GET /auth/me
Header: Authorization: Bearer <token>

GET /auth/api-keys
Header: Authorization: Bearer <token>

POST /auth/api-keys
Header: Authorization: Bearer <token>
Body: { name }
```

