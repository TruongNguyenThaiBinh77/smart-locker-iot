/**
 * api.js – HTTP calls to:
 *   BACKEND_API  : laundry-locker-microservices (orders, auth, lockers)
 *   LOCAL_API    : smart-laundry-locker-iot FastAPI (system state, MQTT logs)
 */

// docker-compose maps the gateway to host port 18080 (API_GATEWAY_PORT).
const BACKEND = import.meta.env.VITE_API_URL || 'http://localhost:18080';
const LOCAL   = import.meta.env.VITE_LOCAL_API_URL || 'http://localhost:8000';

async function req(base, method, path, body = null, token = null) {
  const url = `${base}${path}`;
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (token) opts.headers['Authorization'] = `Bearer ${token}`;
  if (body)  opts.body = JSON.stringify(body);

  try {
    const res  = await fetch(url, opts);
    const data = await res.json();
    return data;
  } catch (err) {
    console.error(`[API] ❌ ${method} ${url}`, err);
    throw err;
  }
}

// Shorthand helpers
const be  = (m, p, b, t) => req(BACKEND, m, p, b, t);
const loc = (m, p, b, t) => req(LOCAL,   m, p, b, t);

// ─── Auth ────────────────────────────────────────────────────
export const sendOtp           = (email)              => be('POST', '/api/auth/email/send-otp', { email });
export const verifyOtp         = (email, otp)         => be('POST', '/api/auth/email/verify-otp', { email, otp });
export const phoneLogin        = (idToken)            => be('POST', '/api/auth/phone-login', { idToken });
export const kioskQuickRegister= (tempToken)          => be('POST', '/api/auth/kiosk/quick-register', { tempToken });

// ─── Services / Promotions ───────────────────────────────────
export const getServices       = (token, lockerId)    => be('GET', `/api/services?lockerId=${lockerId}&category=STORAGE`, null, token);
export const validatePromotionCode = (code, token)        => be('GET', `/api/promotions/validate/${code.toUpperCase()}`, null, token);

// ─── Lockers / Boxes ─────────────────────────────────────────
export const getLockerById     = (lockerId, token)    => be('GET', `/api/lockers/${lockerId}`, null, token);
export const getAllLockers     = (token)              => be('GET', '/api/lockers', null, token);
// Layout (public GET): cells with id/boxNumber/status/cellType — the kiosk's
// source of truth for mapping the box number a customer keys in to a boxId.
export const getLockerLayout   = (lockerId)           => be('GET', `/api/lockers/${lockerId}/layout`);
export const getAvailableBoxes = (lockerId, token)    => be('GET', `/api/lockers/${lockerId}/boxes/available`, null, token);
export const getAllBoxes        = (lockerId, token)    => be('GET', `/api/lockers/${lockerId}/boxes`, null, token);

// ─── Orders ──────────────────────────────────────────────────
export const createOrder       = (token, data)        => be('POST', '/api/orders', data, token);
// createRentalOrder: dùng endpoint /api/orders/rental — gateway gắn X-User-Id từ JWT
// → đơn hàng sẽ được liên kết đúng với user, hiển thị trong mobile app
export const createRentalOrder = (token, data)        => be('POST', '/api/orders/rental', data, token);
export const mockPaymentCheckout = (token, orderId)   => be('POST', '/api/payments/checkout', { orderId, method: 'CASH' }, token);
export const confirmOrder      = (token, orderId)     => be('PUT', `/api/orders/${orderId}/confirm`, null, token);
export const getOrderStatus    = (orderId, token)     => be('GET', `/api/orders/${orderId}/status`, null, token);
export const getOrderByPin     = (pin, token)         => be('GET', `/api/orders/pin/${pin}`, null, token);

// ─── Payments ────────────────────────────────────────────────
export const createPayment     = (token, orderId, method) => be('POST', '/api/payments/create', { orderId, paymentMethod: method }, token);

// ─── IoT (public) ────────────────────────────────────────────
export const verifyPin         = (pinCode, boxId)     => be('POST', '/api/iot/verify-pin', { pinCode, boxId });
export const unlockBox         = (lockerId, pinCode, boxId, actionType) => be('POST', '/api/iot/unlock', { lockerId, pinCode, boxId, actionType });
export const unlockWithCode    = (lockerId, accessCode)         => be('POST', '/api/iot/unlock-with-code', { lockerId, code: accessCode });

// ─── Local FastAPI (IoT Gateway) ─────────────────────────────
export const getSystemInfo     = ()                   => loc('GET', '/system/info');
export const getSystemState    = ()                   => loc('GET', '/system/state');
export const getRecentLogs     = (limit = 50)         => loc('GET', `/logs/recent?limit=${limit}`);
export const getMqttConfig     = ()                   => loc('GET', '/config/mqtt');
export const saveMqttConfig    = (cfg)                => loc('POST', '/config/mqtt', cfg);
export const clearCabinetSetup = ()                   => loc('POST', '/setup/clear');
export const healthCheck       = ()                   => loc('GET', '/health');
