document.addEventListener('DOMContentLoaded', () => {
  const tabLogin = document.getElementById('tab-login');
  const tabSignup = document.getElementById('tab-signup');
  const nameGroup = document.getElementById('name-group');
  const nameInput = document.getElementById('name-input');
  const emailInput = document.getElementById('email-input');
  const passwordInput = document.getElementById('password-input');
  const submitBtn = document.getElementById('submit-btn');
  const btnText = submitBtn.querySelector('.btn-text');
  const spinner = submitBtn.querySelector('.spinner');
  const demoBtn = document.getElementById('demo-btn');
  const errorBox = document.getElementById('error-message');
  const togglePasswordBtn = document.getElementById('toggle-password');
  const authForm = document.getElementById('auth-form');

  let mode = 'login'; // 'login' or 'signup'

  function showError(msg) {
    errorBox.textContent = msg;
    errorBox.style.display = 'block';
  }

  function clearError() {
    errorBox.textContent = '';
    errorBox.style.display = 'none';
  }

  function setLoading(isLoading) {
    submitBtn.disabled = isLoading;
    demoBtn.disabled = isLoading;
    if (isLoading) {
      btnText.style.display = 'none';
      spinner.style.display = 'inline-block';
    } else {
      btnText.style.display = 'inline';
      spinner.style.display = 'none';
    }
  }

  tabLogin.addEventListener('click', () => {
    mode = 'login';
    tabLogin.classList.add('active');
    tabSignup.classList.remove('active');
    nameGroup.style.display = 'none';
    btnText.textContent = 'Log In';
    clearError();
  });

  tabSignup.addEventListener('click', () => {
    mode = 'signup';
    tabSignup.classList.add('active');
    tabLogin.classList.remove('active');
    nameGroup.style.display = 'block';
    btnText.textContent = 'Create Account';
    clearError();
  });

  // Toggle show/hide password
  togglePasswordBtn.addEventListener('click', () => {
    const isPassword = passwordInput.getAttribute('type') === 'password';
    passwordInput.setAttribute('type', isPassword ? 'text' : 'password');
    togglePasswordBtn.innerHTML = isPassword
      ? `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
           <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path>
           <line x1="1" y1="1" x2="23" y2="23"></line>
         </svg>`
      : `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
           <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
           <circle cx="12" cy="12" r="3"></circle>
         </svg>`;
  });

  authForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    clearError();

    const email = emailInput.value.trim();
    const password = passwordInput.value;
    const name = nameInput.value.trim();

    // Client-side quick checks
    if (mode === 'signup' && !name) {
      showError('Please enter your full name');
      return;
    }
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!email || !emailRegex.test(email)) {
      showError('Please enter a valid email address');
      return;
    }
    if (!password || password.length < 8) {
      showError('Password must be at least 8 characters long');
      return;
    }

    setLoading(true);
    const endpoint = mode === 'signup' ? '/api/auth/signup' : '/api/auth/login';
    const payload = mode === 'signup' ? { name, email, password } : { email, password };

    try {
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      const data = await res.json();
      if (!res.ok) {
        showError(data.detail || 'An error occurred. Please try again.');
        setLoading(false);
        return;
      }

      if (data.token) {
        localStorage.setItem('cashpilot_token', data.token);
      }
      if (data.user) {
        localStorage.setItem('cashpilot_user', JSON.stringify(data.user));
      }

      // Success - redirect to dashboard
      window.location.href = '/';
    } catch (err) {
      showError('Unable to connect to server. Please check your connection.');
      setLoading(false);
    }
  });

  // Demo login
  demoBtn.addEventListener('click', async () => {
    clearError();
    setLoading(true);
    try {
      const res = await fetch('/api/auth/demo', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      const data = await res.json();
      if (!res.ok) {
        showError(data.detail || 'Could not log in with demo account.');
        setLoading(false);
        return;
      }
      if (data.token) {
        localStorage.setItem('cashpilot_token', data.token);
      }
      if (data.user) {
        localStorage.setItem('cashpilot_user', JSON.stringify(data.user));
      }
      window.location.href = '/';
    } catch (err) {
      showError('Failed to log in with demo account.');
      setLoading(false);
    }
  });
});
