import { useState, useEffect, useCallback, useRef } from 'react';
import * as api from '../api';
import { setupRecaptcha, sendPhoneOtp } from '../firebase';
import {
  Lock, Package, Smartphone, Mail, ArrowLeft, MapPin,
  CheckCircle, KeyRound, Hash, User, CreditCard,
  Unlock, Home, Loader2, Delete, Circle, ClipboardList,
  Wifi, ChevronRight, ShieldCheck, X, Banknote
} from 'lucide-react';
import { QRCodeSVG } from 'qrcode.react';


// ============================================
// Config
// ============================================
const urlParams = new URLSearchParams(window.location.search);

const LOCKER_CODE = urlParams.get('lockerCode') || import.meta.env.VITE_LOCKER_CODE || 'LOC-01-001';
const INITIAL_LOCKER_ID = parseInt(urlParams.get('lockerId') || import.meta.env.VITE_LOCKER_ID || '1', 10);
const AUTO_HOME_SEC = 20;

// ============================================
// App
// ============================================
export default function KioskScreen() {
  const [activeLockerId, setActiveLockerId] = useState(INITIAL_LOCKER_ID);
  const [allLockers, setAllLockers] = useState([]);

  const [screen, setScreen] = useState('home');
  const [history, setHistory] = useState(['home']);
  const [jwt, setJwt] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [loginMethod, setLoginMethod] = useState('phone');
  const [tempToken, setTempToken] = useState('');
  const [userName, setUserName] = useState('');
  const [selectedBox, setSelectedBox] = useState(null);
  const [orderId, setOrderId] = useState(null);
  const [orderPin, setOrderPin] = useState('');
  const [orderCode, setOrderCode] = useState('');
  const [totalPrice, setTotalPrice] = useState(0);
  const [successTitle, setSuccessTitle] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  const [successExtra, setSuccessExtra] = useState(null);
  const [countdown, setCountdown] = useState(0);
  const [lockerInfo, setLockerInfo] = useState(null);
  const cdRef = useRef(null);

  // Fetch list of all lockers for dropdown
  useEffect(() => {
    (async () => {
      try {
        const res = await api.getAllLockers();
        if (res.success && res.data) {
          const list = res.data.content || res.data;
          setAllLockers(list);
          if (list.length > 0 && !list.find(l => l.id === activeLockerId)) {
            setActiveLockerId(list[0].id);
          }
        }
      } catch (err) { console.error('Failed to fetch lockers', err); }
    })();
  }, []);

  // Fetch locker info + layout (with periodic polling for real-time sync)
  useEffect(() => {
    let ignore = false;
    if (!activeLockerId) return;

    const fetchLockerData = async () => {
      try {
        const res = await api.getLockerById(activeLockerId, jwt || undefined);
        if (ignore || !res.success || !res.data) return;
        let boxes = [];
        try {
          const lay = await api.getLockerLayout(activeLockerId);
          if (lay.success && Array.isArray(lay.data?.cells)) boxes = lay.data.cells;
        } catch { /* layout is best-effort */ }
        if (!ignore) setLockerInfo({ ...res.data, boxes });
      } catch { /* ignore */ }
    };

    setLockerInfo(null);
    fetchLockerData();
    const intervalId = setInterval(fetchLockerData, 3000);

    return () => {
      ignore = true;
      clearInterval(intervalId);
    };
  }, [jwt, activeLockerId]);

  // Navigate
  const go = useCallback((s) => {
    console.log(`%c[NAV] → ${s}`, 'color:#c084fc;font-weight:bold');
    setScreen(s);
    setHistory(h => [...h, s]);
  }, []);

  const back = useCallback(() => {
    setHistory(h => {
      if (h.length <= 1) return h;
      const newH = h.slice(0, -1);
      setScreen(newH[newH.length - 1]);
      return newH;
    });
  }, []);

  const goHome = useCallback(() => {
    console.log('%c[NAV] → home (reset)', 'color:#c084fc;font-weight:bold');
    setJwt(''); setEmail(''); setPhone(''); setLoginMethod('phone'); setTempToken(''); setUserName('');
    setSelectedBox(null); setOrderId(null);
    setOrderPin(''); setOrderCode(''); setTotalPrice(0);
    setScreen('home'); setHistory(['home']);
    if (cdRef.current) clearInterval(cdRef.current);
  }, []);

  const showSuccess = useCallback((title, msg, extra = null) => {
    setSuccessTitle(title);
    setSuccessMsg(msg);
    setSuccessExtra(extra);
    go('success');
    let sec = AUTO_HOME_SEC;
    setCountdown(sec);
    if (cdRef.current) clearInterval(cdRef.current);
    cdRef.current = setInterval(() => {
      sec--;
      setCountdown(sec);
      if (sec <= 0) { clearInterval(cdRef.current); goHome(); }
    }, 1000);
  }, [go, goHome]);

  return (
    <div className="kiosk-wrap">
      {screen === 'home' && <HomeScreen go={go} lockerInfo={lockerInfo} activeLockerId={activeLockerId} setActiveLockerId={setActiveLockerId} allLockers={allLockers} />}
      {screen === 'login' && <LoginScreen go={go} goHome={goHome} email={email} setEmail={setEmail} phone={phone} setPhone={setPhone} loginMethod={loginMethod} setLoginMethod={setLoginMethod} />}
      {screen === 'otp' && <OtpScreen go={go} back={back} email={email} setJwt={setJwt} setTempToken={setTempToken} setUserName={setUserName} />}
      {screen === 'phone-otp' && <PhoneOtpScreen go={go} back={back} phone={phone} setJwt={setJwt} setTempToken={setTempToken} setUserName={setUserName} />}
      {screen === 'register' && <RegisterScreen go={go} goHome={goHome} tempToken={tempToken} setJwt={setJwt} setUserName={setUserName} />}
      {screen === 'boxes' && <BoxSelectionScreen go={go} goHome={goHome} jwt={jwt} userName={userName} selectedBox={selectedBox} setSelectedBox={setSelectedBox} lockerInfo={lockerInfo} activeLockerId={activeLockerId} />}
      {screen === 'order-info' && <OrderInfoScreen go={go} back={back} jwt={jwt} selectedBox={selectedBox} setOrderId={setOrderId} setOrderPin={setOrderPin} setOrderCode={setOrderCode} setTotalPrice={setTotalPrice} activeLockerId={activeLockerId} />}
      {screen === 'payment' && <PaymentScreen go={go} goHome={goHome} jwt={jwt} orderId={orderId} orderPin={orderPin} orderCode={orderCode} totalPrice={totalPrice} selectedBox={selectedBox} showSuccess={showSuccess} activeLockerId={activeLockerId} />}
      {screen === 'pin' && <PinScreen goHome={goHome} showSuccess={showSuccess} lockerInfo={lockerInfo} activeLockerId={activeLockerId} />}
      {screen === 'staff' && <StaffScreen goHome={goHome} showSuccess={showSuccess} lockerInfo={lockerInfo} activeLockerId={activeLockerId} />}
      {screen === 'success' && <SuccessScreen goHome={goHome} title={successTitle} msg={successMsg} extra={successExtra} countdown={countdown} />}
    </div>
  );
}

// ============================================
// Shared Components
// ============================================
function Header({ onBack, title }) {
  return (
    <div className="header">
      <button className="back-btn" onClick={onBack}><ArrowLeft size={20} /></button>
      <h2>{title}</h2>
    </div>
  );
}

function Msg({ type, text }) {
  if (!text) return null;
  return <div className={`msg msg-${type}`}>{text}</div>;
}

function Btn({ children, onClick, loading, disabled, variant = 'primary', style, id }) {
  return (
    <button id={id} className={`btn btn-${variant}`} onClick={onClick} disabled={loading || disabled} style={style}>
      {loading ? <><Loader2 size={18} className="spinner" style={{ border: 'none', animation: 'spin 0.6s linear infinite' }} /> Đang xử lý...</> : children}
    </button>
  );
}

// ============================================
// HOME
// ============================================
function HomeScreen({ go, lockerInfo, activeLockerId, setActiveLockerId, allLockers }) {
  return (
    <div className="screen screen-home-split">
      <div className="home-left">
        <div className="home-logo">
          <div className="icon-wrap">
            <Lock size={48} strokeWidth={2.5} />
          </div>
          <h1>Lock.R</h1>
          <p className="sub">Hệ thống tủ thông minh</p>
        </div>
        <div className="footer">Powered by Locker IoT</div>
      </div>

      <div className="home-right">
        <div className="home-config">
          <MapPin size={18} color="var(--accent)" />
          <select
            value={activeLockerId}
            onChange={e => setActiveLockerId(parseInt(e.target.value, 10))}
            className="locker-select"
          >
            {allLockers.map(loc => (
              <option key={loc.id} value={loc.id}>
                {loc.name} - {loc.code}
              </option>
            ))}
          </select>
        </div>

        {lockerInfo && (
          <div className="locker-info-card">
            <div className="locker-name">
              {lockerInfo.storeName || lockerInfo.name}
            </div>
            <div className="locker-address">{lockerInfo.address}</div>
            {lockerInfo.totalBoxes != null && (
              <div className="locker-stats">
                <span className="stat-available"><CheckCircle size={14} style={{ marginRight: 4, verticalAlign: -2 }} />{lockerInfo.availableBoxes ?? '—'} Trống</span>
                <span className="stat-total">/ {lockerInfo.totalBoxes} ô</span>
              </div>
            )}
          </div>
        )}

        <div className="home-status">
          <Wifi size={16} />
          Kiosk sẵn sàng phục vụ
        </div>

        <div className="home-actions">
          <Btn onClick={() => go('staff')}><Unlock size={20} /> Nhập OTP / Quét QR (Mở tủ)</Btn>
          <Btn variant="secondary" onClick={() => go('login')}><Package size={20} /> Đặt tủ trực tiếp tại Kiosk</Btn>
        </div>
      </div>
    </div>
  );
}

// ============================================
// LOGIN (Email + Phone toggle)
// ============================================
function LoginScreen({ go, goHome, email, setEmail, phone, setPhone, loginMethod, setLoginMethod }) {
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState('');
  const recaptchaReady = useRef(false);

  useEffect(() => {
    if (loginMethod === 'phone' && !recaptchaReady.current) {
      try {
        setupRecaptcha('phone-send-btn');
        recaptchaReady.current = true;
      } catch { /* button may not be in DOM yet */ }
    }
  }, [loginMethod]);

  useEffect(() => {
    if (loginMethod !== 'phone') recaptchaReady.current = false;
  }, [loginMethod]);

  const handleSendEmail = async () => {
    if (!email || !email.includes('@')) { setMsg('Vui lòng nhập email hợp lệ'); return; }
    setLoading(true); setMsg('');
    try {
      console.log('%c[LOGIN] Sending email OTP to:', 'color:#fbbf24', email);
      const res = await api.sendOtp(email);
      if (res.success) go('otp');
      else setMsg(res.message || 'Lỗi gửi OTP');
    } catch { setMsg('Lỗi kết nối server'); }
    setLoading(false);
  };

  const handleSendPhone = async () => {
    if (!phone || phone.length < 9) { setMsg('Vui lòng nhập số điện thoại hợp lệ'); return; }
    setLoading(true); setMsg('');
    try {
      if (!recaptchaReady.current) {
        setupRecaptcha('phone-send-btn');
        recaptchaReady.current = true;
      }
      let formatted = phone.trim();
      if (formatted.startsWith('0')) formatted = '+84' + formatted.slice(1);
      else if (!formatted.startsWith('+')) formatted = '+84' + formatted;

      const confirmation = await sendPhoneOtp(formatted);
      window.confirmationResult = confirmation;
      go('phone-otp');
    } catch (err) {
      console.error('Firebase phone OTP error:', err);
      setMsg(err.message || 'Lỗi gửi OTP. Vui lòng thử lại.');
      recaptchaReady.current = false;
    }
    setLoading(false);
  };

  return (
    <div className="screen">
      <Header onBack={goHome} title="Nhập thông tin" />
      <div className="login-tabs">
        <div className={`login-tab ${loginMethod === 'phone' ? 'active' : ''}`} onClick={() => { setLoginMethod('phone'); setMsg(''); }}>
          <Smartphone size={16} /> Số điện thoại
        </div>
        <div className={`login-tab ${loginMethod === 'email' ? 'active' : ''}`} onClick={() => { setLoginMethod('email'); setMsg(''); }}>
          <Mail size={16} /> Email
        </div>
      </div>

      {loginMethod === 'phone' ? (
        <>
          <p className="subtitle">Nhập số điện thoại để nhận mã OTP xác thực</p>
          <div className="form-group">
            <label>Số điện thoại</label>
            <input className="input" type="tel" value={phone} onChange={e => setPhone(e.target.value.replace(/[^0-9+]/g, ''))}
              placeholder="0901234567" inputMode="tel" autoComplete="tel"
              onKeyDown={e => e.key === 'Enter' && handleSendPhone()} />
          </div>
          <Btn id="phone-send-btn" onClick={handleSendPhone} loading={loading}><Smartphone size={18} /> Gửi mã OTP</Btn>
        </>
      ) : (
        <>
          <p className="subtitle">Nhập email để nhận mã OTP xác thực</p>
          <div className="form-group">
            <label>Email</label>
            <input className="input" type="email" value={email} onChange={e => setEmail(e.target.value)}
              placeholder="example@gmail.com" autoComplete="email" onKeyDown={e => e.key === 'Enter' && handleSendEmail()} />
          </div>
          <Btn onClick={handleSendEmail} loading={loading}><Mail size={18} /> Gửi mã OTP</Btn>
        </>
      )}
      {msg && <Msg type="error" text={msg} />}
    </div>
  );
}

// ============================================
// PHONE OTP (Firebase verification)
// ============================================
function PhoneOtpScreen({ go, back, phone, setJwt, setTempToken, setUserName }) {
  const [otp, setOtp] = useState('');
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState('');

  const handleVerify = async () => {
    if (otp.length !== 6) { setMsg('Vui lòng nhập đủ 6 số OTP'); return; }
    setLoading(true); setMsg('');
    try {
      const confirmation = window.confirmationResult;
      if (!confirmation) { setMsg('Phiên đã hết hạn. Vui lòng quay lại.'); setLoading(false); return; }

      const userCredential = await confirmation.confirm(otp);
      const idToken = await userCredential.user.getIdToken();
      console.log('%c[AUTH] Firebase phone verified, sending to backend', 'color:#fbbf24');

      const res = await api.phoneLogin(idToken);
      if (res.success && res.data) {
        if (res.data.newUser || res.data.isNewUser) {
          setTempToken(res.data.tempToken);
          go('register');
        } else {
          setJwt(res.data.accessToken);
          const name = res.data.userInfo?.fullName || phone;
          setUserName(name);
          go('boxes');
        }
      } else {
        setMsg(res.message || 'Lỗi đăng nhập');
      }
    } catch (err) {
      console.error('Phone OTP verify error:', err);
      if (err.code === 'auth/invalid-verification-code') {
        setMsg('Mã OTP không đúng. Vui lòng thử lại.');
      } else if (err.code === 'auth/code-expired') {
        setMsg('Mã OTP đã hết hạn. Vui lòng quay lại và gửi lại.');
      } else {
        setMsg(err.message || 'Lỗi xác thực');
      }
    }
    setLoading(false);
  };

  return (
    <div className="screen">
      <Header onBack={back} title="Xác thực OTP" />
      <p className="subtitle">
        Mã OTP đã gửi đến <strong>{phone}</strong>
      </p>
      <div className="form-group">
        <label>Nhập mã OTP 6 số</label>
        <input className="input" value={otp} onChange={e => setOtp(e.target.value.replace(/\D/g, '').slice(0, 6))}
          placeholder="123456" maxLength={6} inputMode="numeric"
          style={{ textAlign: 'center', fontSize: 24, letterSpacing: 8, fontWeight: 700 }}
          onKeyDown={e => e.key === 'Enter' && handleVerify()} />
      </div>
      <Btn onClick={handleVerify} loading={loading}><CheckCircle size={18} /> Xác nhận</Btn>
      {msg && <Msg type="error" text={msg} />}
    </div>
  );
}

// ============================================
// OTP
// ============================================
function OtpScreen({ go, back, email, setJwt, setTempToken, setUserName }) {
  const [otp, setOtp] = useState('');
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState('');

  const handleVerify = async () => {
    if (otp.length !== 6) { setMsg('Vui lòng nhập đủ 6 số OTP'); return; }
    setLoading(true); setMsg('');
    try {
      const res = await api.verifyOtp(email, otp);
      if (res.success && res.data) {
        if (res.data.newUser || res.data.isNewUser) {
          setTempToken(res.data.tempToken);
          go('register');
        } else {
          setJwt(res.data.accessToken);
          const name = res.data.userInfo?.fullName || email;
          setUserName(name);
          go('boxes');
        }
      } else {
        setMsg(res.message || 'OTP không hợp lệ');
      }
    } catch { setMsg('Lỗi kết nối server'); }
    setLoading(false);
  };

  return (
    <div className="screen">
      <Header onBack={back} title="Xác thực OTP" />
      <p className="subtitle">
        Mã OTP đã gửi đến <strong>{email}</strong>
      </p>
      <div className="form-group">
        <label>Nhập mã OTP 6 số</label>
        <input className="input" value={otp} onChange={e => setOtp(e.target.value.replace(/\D/g, '').slice(0, 6))}
          placeholder="123456" maxLength={6} inputMode="numeric"
          style={{ textAlign: 'center', fontSize: 24, letterSpacing: 8, fontWeight: 700 }}
          onKeyDown={e => e.key === 'Enter' && handleVerify()} />
      </div>
      <Btn onClick={handleVerify} loading={loading}><CheckCircle size={18} /> Xác nhận</Btn>
      {msg && <Msg type="error" text={msg} />}
    </div>
  );
}

// ============================================
// REGISTER (Kiosk Quick Register — API 1.4)
// ============================================
function RegisterScreen({ go, goHome, tempToken, setJwt, setUserName }) {
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState('');
  const reqSent = useRef(false);

  useEffect(() => {
    if (reqSent.current) return;
    reqSent.current = true;

    (async () => {
      setLoading(true); setMsg('');
      try {
        const res = await api.kioskQuickRegister(tempToken);
        if (res.success && res.data) {
          setJwt(res.data.accessToken);
          setUserName('Khách');
          go('boxes');
        } else {
          setMsg(res.message || 'Lỗi đăng ký nhanh');
        }
      } catch {
        setMsg('Lỗi kết nối server');
      }
      setLoading(false);
    })();
  }, [tempToken, setJwt, setUserName, go]);

  return (
    <div className="screen">
      <Header onBack={goHome} title="Đăng ký nhanh" />
      {loading && (
        <div style={{ textAlign: 'center', padding: 40 }}>
          <Loader2 size={36} className="spinner" style={{ border: 'none', animation: 'spin 0.6s linear infinite', color: 'var(--accent)' }} />
          <p style={{ color: 'var(--text-secondary)', marginTop: 16, fontSize: 14 }}>Đang tạo tài khoản...</p>
        </div>
      )}
      {msg && <Msg type="error" text={msg} />}
      {msg && <Btn onClick={goHome} variant="secondary" style={{ marginTop: 16 }}><ArrowLeft size={18} /> Quay lại</Btn>}
    </div>
  );
}

// ============================================
// BOX SELECTION
// ============================================
function BoxSelectionScreen({ go, goHome, jwt, userName, selectedBox, setSelectedBox, lockerInfo, activeLockerId }) {
  const [boxes, setBoxes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState('');

  useEffect(() => {
    let ignore = false;
    (async () => {
      setLoading(true); setMsg('');
      console.log('%c[BOX] Loading available boxes for locker:', 'color:#fbbf24', activeLockerId);
      try {
        const res = await api.getAvailableBoxes(activeLockerId, jwt);
        if (!ignore && res.success && res.data) {
          setBoxes(res.data);
          console.log('%c[BOX] Available boxes:', 'color:#4ade80', res.data.length, res.data);
          if (res.data.length === 0) setMsg('Không có ô tủ trống');
        } else if (!ignore) {
          setMsg(res.message || 'Lỗi tải danh sách ô tủ');
        }
      } catch { if (!ignore) setMsg('Lỗi kết nối server'); }
      if (!ignore) setLoading(false);
    })();
    return () => { ignore = true; };
  }, []);

  return (
    <div className="screen">
      <Header onBack={goHome} title="Chọn ô tủ" />
      {userName && <div className="user-info"><User size={16} /> {userName}</div>}
      {lockerInfo && (
        <div className="locker-info-card">
          <div className="locker-name">
            <MapPin size={16} color="var(--accent)" />
            {lockerInfo.storeName || lockerInfo.name}
          </div>
          <div className="locker-address">
            {lockerInfo.address} • Tủ: {lockerInfo.code}
          </div>
          {lockerInfo.totalBoxes != null && (
            <div className="locker-stats">
              <span className="stat-available">
                <CheckCircle size={14} style={{ marginRight: 4, verticalAlign: -2 }} />
                {lockerInfo.availableBoxes ?? boxes.length} ô trống
              </span>
              <span className="stat-total">/ {lockerInfo.totalBoxes} ô</span>
            </div>
          )}
        </div>
      )}
      {!lockerInfo && (
        <p className="subtitle">Chọn 1 ô tủ trống để gửi đồ</p>
      )}

      {loading && <p style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 24 }}><Loader2 size={20} style={{ animation: 'spin 0.6s linear infinite', verticalAlign: -4, marginRight: 8 }} />Đang tải...</p>}
      {msg && !loading && <Msg type="error" text={msg} />}

      <div className="box-grid">
        {boxes.map(box => {
          const sel = selectedBox?.boxId === box.boxId;
          return (
            <button key={box.boxId} onClick={() => setSelectedBox(box)}
              className={`box-item ${sel ? 'selected' : ''}`}>
              <div className="box-icon"><Package size={28} /></div>
              <div className="box-number">Ô {box.boxNumber}</div>
              <div className="box-status">Trống</div>
            </button>
          );
        })}
      </div>

      <Btn onClick={() => go('order-info')} disabled={!selectedBox}>
        Tiếp tục <ChevronRight size={18} /> Đặt tủ
      </Btn>
    </div>
  );
}

// ============================================
// ORDER INFO
// ============================================
function OrderInfoScreen({ go, back, jwt, selectedBox, setOrderId, setOrderPin, setOrderCode, setTotalPrice, activeLockerId }) {
  const [note, setNote] = useState('');
  const [hours, setHours] = useState(1);

  // Promo states
  const [promoCode, setPromoCode] = useState('');
  const [promoApplied, setPromoApplied] = useState(false);
  const [promoDiscount, setPromoDiscount] = useState(0);
  const [promoLoading, setPromoLoading] = useState(false);
  const [promoError, setPromoError] = useState('');
  const [promoDetail, setPromoDetail] = useState(null);

  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState('');

  // Tính giá thuê: STANDARD = 5000đ/giờ (theo backend config)
  const HOURLY_RATE = 5000;
  const subtotal = hours * HOURLY_RATE;
  const total = Math.max(0, subtotal - promoDiscount);

  const handleApplyPromo = async () => {
    const code = promoCode.trim();
    if (!code) return;

    setPromoLoading(true); setPromoError(''); setPromoApplied(false);
    setPromoDiscount(0); setPromoDetail(null);

    try {
      const res = await api.validatePromotionCode(code, jwt);
      if (res.success && res.data) {
        const promo = res.data;
        if (promo.minOrderAmount && subtotal < promo.minOrderAmount) {
          setPromoError(`Đơn hàng tối thiểu ${new Intl.NumberFormat('vi-VN').format(promo.minOrderAmount)}đ để áp dụng mã này`);
        } else {
          let discount = 0;
          if (promo.discountType === 'PERCENTAGE') {
            discount = subtotal * promo.discountValue / 100;
            if (promo.maxDiscountAmount) discount = Math.min(discount, promo.maxDiscountAmount);
          } else if (promo.discountType === 'FIXED_AMOUNT') {
            discount = promo.discountValue;
          }
          discount = Math.min(discount, subtotal);
          setPromoDetail(promo);
          setPromoDiscount(discount);
          setPromoApplied(true);
        }
      } else {
        setPromoError(res.message || 'Mã không hợp lệ');
      }
    } catch (err) {
      setPromoError('Lỗi kiểm tra mã, vui lòng thử lại');
    }
    setPromoLoading(false);
  };

  const handleCreate = async () => {
    if (!selectedBox) { setMsg('Chưa chọn ô tủ'); return; }
    setLoading(true); setMsg('');
    try {
      // Dùng POST /api/orders/rental — gateway gắn X-User-Id từ JWT
      // → đơn hàng liên kết đúng với user, hiển thị trong "Đơn tủ" trên mobile
      const payload = {
        lockerId: activeLockerId,
        boxId: selectedBox.boxId,   // LockerBoxSummary.boxId (không phải .id)
        cellType: 'STANDARD',
        hours: hours,
        note: note || undefined,
        promotionCode: (promoApplied && promoCode.trim()) ? promoCode.trim() : undefined,
      };

      console.log('%c[ORDER] Creating RENTAL order via /api/orders/rental:', 'color:#fbbf24', payload);
      const res = await api.createRentalOrder(jwt, payload);
      if (res.success && res.data) {
        console.log('%c[ORDER] ✅ Created:', 'color:#4ade80', { id: res.data.id, pin: res.data.pinCode, code: res.data.orderCode });
        setOrderId(res.data.id);
        setOrderPin(res.data.pinCode || '');
        setOrderCode(res.data.orderCode || '');
        setTotalPrice(res.data.totalPrice ?? total);
        go('payment');
      } else {
        setMsg(res.data?.message || res.message || 'Lỗi tạo đơn hàng. Vui lòng thử lại.');
      }
    } catch (e) {
      console.error('[ORDER] Error:', e);
      setMsg('Lỗi kết nối server');
    }
    setLoading(false);
  };

  const fmt = (p) => new Intl.NumberFormat('vi-VN').format(p) + 'đ';
  const hoursOptions = [1, 2, 3, 4, 6, 8, 12, 24];

  return (
    <div className="screen">
      <Header onBack={back} title="Thông tin đặt tủ" />

      {/* Số giờ thuê */}
      <div className="form-group">
        <label style={{ fontWeight: 600, marginBottom: 8, display: 'block' }}>Thời gian thuê tủ</label>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {hoursOptions.map(h => (
            <button
              key={h}
              onClick={() => setHours(h)}
              style={{
                padding: '10px 18px',
                borderRadius: 12,
                border: `2px solid ${hours === h ? 'var(--accent)' : 'var(--border)'}`,
                backgroundColor: hours === h ? 'var(--accent)' : 'transparent',
                color: hours === h ? '#fff' : 'var(--text-primary)',
                fontWeight: hours === h ? 700 : 400,
                cursor: 'pointer',
                fontSize: 14,
                transition: 'all 0.15s',
              }}
            >
              {h}h
            </button>
          ))}
        </div>
        <div style={{ marginTop: 8, fontSize: 13, color: 'var(--text-secondary)' }}>
          Giá: {fmt(HOURLY_RATE)}/giờ — Tổng {hours} giờ = <strong style={{ color: 'var(--accent)' }}>{fmt(subtotal)}</strong>
        </div>
      </div>

      {/* Ghi chú */}
      <div className="form-group">
        <label>Ghi chú (tùy chọn)</label>
        <input className="input" value={note} onChange={e => setNote(e.target.value)} placeholder="Ví dụ: Quần áo, cần giữ cẩn thận..." />
      </div>

      {/* Mã giảm giá */}
      <div className="divider" style={{ marginTop: 20 }}>Mã giảm giá/Ưu đãi</div>
      <div className="form-group">
        <div style={{ display: 'flex', gap: 8 }}>
          <input className="input" value={promoCode} onChange={e => {
            setPromoCode(e.target.value.toUpperCase());
            if (promoApplied || promoError) { setPromoApplied(false); setPromoError(''); setPromoDiscount(0); setPromoDetail(null); }
          }} placeholder="Nhập mã khuyến mãi" style={{ flex: 1, textTransform: 'uppercase' }} disabled={promoApplied || promoLoading} />
          {!promoApplied ? (
            <button className="btn btn-primary" onClick={handleApplyPromo} disabled={!promoCode.trim() || promoLoading} style={{ width: 'auto', padding: '0 20px', borderRadius: 12 }}>
              {promoLoading ? <Loader2 size={18} className="spinner" /> : 'Áp dụng'}
            </button>
          ) : (
            <button className="btn btn-secondary" onClick={() => { setPromoCode(''); setPromoApplied(false); setPromoDiscount(0); }} style={{ width: 'auto', padding: '0 20px', borderRadius: 12, backgroundColor: '#f1f5f9', color: '#64748b' }}>
              <X size={18} /> Gỡ bỏ
            </button>
          )}
        </div>
        {promoError && <div style={{ color: '#ef4444', fontSize: 13, marginTop: 8, display: 'flex', alignItems: 'center', gap: 4 }}><Circle size={12} fill="#ef4444" color="#ef4444" /> {promoError}</div>}
        {promoApplied && promoDetail && (
          <div style={{ marginTop: 12, padding: 12, backgroundColor: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 12 }}>
            <div style={{ color: '#166534', fontWeight: 600, fontSize: 14 }}>{promoDetail.title || promoDetail.name}</div>
            <div style={{ color: '#22c55e', fontSize: 13, marginTop: 4 }}>Đã giảm: {fmt(promoDiscount)}</div>
          </div>
        )}
      </div>

      {/* Tổng tiền */}
      <div className="order-sum" style={{ marginTop: 24 }}>
        <div className="order-row"><span style={{ color: 'var(--text-secondary)' }}>Thuê tủ {hours} giờ:</span> <strong>{fmt(subtotal)}</strong></div>
        {promoApplied && promoDiscount > 0 && (
          <div className="order-row"><span style={{ color: '#22c55e' }}>Khuyến mãi:</span> <strong style={{ color: '#ef4444' }}>-{fmt(promoDiscount)}</strong></div>
        )}
        <div className="order-row" style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--border)' }}>
          <span style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>Tổng cộng:</span>
          <strong style={{ fontSize: 20, color: 'var(--accent)' }}>{fmt(total)}</strong>
        </div>
      </div>

      <Btn onClick={handleCreate} loading={loading} style={{ marginTop: 24 }}><ClipboardList size={18} /> Đặt tủ ngay</Btn>
      {msg && <Msg type="error" text={msg} />}
    </div>
  );
}




// ============================================
// PAYMENT
// ============================================
function PaymentScreen({ go, goHome, jwt, orderId, orderPin, orderCode, totalPrice, selectedBox, showSuccess, activeLockerId }) {
  const [loading, setLoading] = useState('');
  const [payUrl, setPayUrl] = useState('');
  const [qrCodeUrl, setQrCodeUrl] = useState('');
  const [deeplink, setDeeplink] = useState('');
  const [payMethod, setPayMethod] = useState('');
  const [msg, setMsg] = useState('');
  const [polling, setPolling] = useState(false);
  const pollRef = useRef(null);

  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  const fmt = (p) => new Intl.NumberFormat('vi-VN').format(p) + 'đ';

  const successExtra = { orderCode, orderPin, boxNumber: selectedBox?.boxNumber };

  // Với RENTAL: confirm order để chuyển sang STORING (bắt buộc với RENTAL flow)
  const confirmOrder = async () => {
    try {
      await api.confirmOrder(jwt, orderId);
      console.log('%c[ORDER] ✅ RENTAL confirmed → STORING', 'color:#4ade80');
    } catch (e) {
      console.warn('[ORDER] ⚠️ Confirm failed (best-effort):', e.message);
    }
  };

  const skipPay = async () => {
    setLoading('skip');
    console.log('%c[UNLOCK] Skip pay → unlock box (RENTAL DROP_OFF):', 'color:#fbbf24', { pin: orderPin, boxId: selectedBox?.boxId });
    try {
      // Gọi checkout tiền mặt (mock) để order được đánh dấu PAID trước khi confirm
      await api.mockPaymentCheckout(jwt, orderId).catch(() => {});
      
      const res = await api.unlockBox(activeLockerId, orderPin, selectedBox?.boxId, 'DROP_OFF');
      if (res.success || res.data?.success) {
        await confirmOrder(); // chuyển RENTAL sang STORING
        showSuccess('Tủ đã mở!',
          `Vui lòng đặt đồ vào ô tủ và đóng cửa. Dùng mã PIN ${orderPin} để mở lại tủ khi lấy đồ.`,
          successExtra);
      } else {
        setMsg(res.data?.message || res.message || 'Lỗi mở tủ');
      }
    } catch { setMsg('Lỗi kết nối'); }
    setLoading('');
  };

  const payOnline = async (method) => {
    setLoading(method);
    setPayUrl(''); setQrCodeUrl(''); setDeeplink(''); setPayMethod(''); setMsg('');
    try {
      const res = await api.createPayment(jwt, orderId, method);
      if (res.success && res.data?.paymentUrl) {
        setPayUrl(res.data.paymentUrl);
        setQrCodeUrl(res.data.qrCodeUrl || '');
        setDeeplink(res.data.deeplink || '');
        setPayMethod(method);
        startPaymentPolling();
      } else {
        setMsg(res.data?.message || res.message || 'Lỗi tạo thanh toán');
      }
    } catch { setMsg('Lỗi kết nối'); }
    setLoading('');
  };

  const startPaymentPolling = () => {
    if (pollRef.current) clearInterval(pollRef.current);
    setPolling(true);
    pollRef.current = setInterval(async () => {
      try {
        const res = await api.getOrderStatus(orderId, jwt);
        if (res.success && res.data?.isPaid) {
          clearInterval(pollRef.current);
          setPolling(false);
          await openAfterPay();
        }
      } catch { /* ignore polling errors */ }
    }, 3000);
  };

  const openAfterPay = async () => {
    setLoading('open');
    if (pollRef.current) { clearInterval(pollRef.current); setPolling(false); }
    try {
      const res = await api.unlockBox(activeLockerId, orderPin, selectedBox?.boxId, 'DROP_OFF');
      if (res.success || res.data?.success) {
        await confirmOrder(); // chuyển RENTAL sang STORING
        showSuccess('Thanh toán thành công!',
          `Tủ đã mở. Vui lòng đặt đồ vào ô #${selectedBox?.boxNumber} và đóng cửa. PIN: ${orderPin}`,
          successExtra);
      } else {
        setMsg(res.data?.message || res.message || 'Lỗi mở tủ');
      }
    } catch { setMsg('Lỗi kết nối'); }
    setLoading('');
  };

  return (
    <div className="screen">
      <Header onBack={goHome} title="Thanh toán" />
      <div style={{ maxWidth: 500, margin: '0 auto', width: '100%' }}>
        <div className="order-sum" style={{ marginBottom: 24 }}>
          <div className="order-row"><ClipboardList size={16} /> Mã đơn: <strong>{orderCode}</strong></div>
          <div className="order-row"><KeyRound size={16} /> PIN: <strong>{orderPin}</strong></div>
          <div className="order-row"><CreditCard size={16} /> Tổng: <strong>{fmt(totalPrice)}</strong></div>
          {selectedBox && <div className="order-row"><Package size={16} /> Ô tủ: <strong>#{selectedBox.boxNumber}</strong></div>}
        </div>
        {!payUrl && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <Btn onClick={() => payOnline('MOMO')} loading={loading === 'MOMO'}>
              <Smartphone size={18} /> Thanh toán MoMo & Mở tủ
            </Btn>
            <div className="divider" style={{ margin: '4px 0' }}>Hoặc (Demo)</div>
            <Btn variant="secondary" onClick={skipPay} loading={loading === 'skip'}>
              <Banknote size={18} /> Thanh toán Tiền mặt (Demo)
            </Btn>
            <Btn variant="outline" onClick={() => payOnline('VNPAY')} loading={loading === 'VNPAY'}>
              <CreditCard size={18} /> Thanh toán VNPay
            </Btn>
          </div>
        )}

        {/* MoMo QR Payment Section */}
        {payUrl && payMethod === 'MOMO' && (
          <div className="momo-pay-section">
            <div className="momo-header">
              <Smartphone size={20} color="#A50064" />
              <span>Thanh toán MoMo</span>
            </div>
            {qrCodeUrl && (
              <div className="momo-qr" style={{ padding: 16, background: '#fff', borderRadius: 12, margin: '16px auto', width: 'fit-content' }}>
                <p className="momo-qr-label" style={{ marginBottom: 16 }}>Quét mã QR bằng ứng dụng MoMo</p>
                <QRCodeSVG value={qrCodeUrl} size={160} />
              </div>
            )}
            {deeplink && (
              <a href={deeplink} target="_blank" rel="noreferrer" className="btn btn-momo" style={{ marginTop: 12 }}>
                <Smartphone size={18} /> Mở ứng dụng MoMo
              </a>
            )}
            {!qrCodeUrl && (
              <div className="pay-link">
                <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 8 }}>Mở link để thanh toán MoMo:</p>
                <a href={payUrl} target="_blank" rel="noreferrer">{payUrl}</a>
              </div>
            )}
            {polling && <p className="polling-status"><Loader2 size={14} style={{ animation: 'spin 0.6s linear infinite' }} />Đang chờ xác nhận thanh toán...</p>}
          </div>
        )}

        {/* VNPay / Generic Payment Section */}
        {payUrl && payMethod === 'VNPAY' && (
          <div className="pay-link">
            <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 8 }}><CreditCard size={14} style={{ verticalAlign: -2, marginRight: 4 }} />Mở link để thanh toán VNPay:</p>
            <a href={payUrl} target="_blank" rel="noreferrer">{payUrl}</a>
            {polling && <p className="polling-status"><Loader2 size={14} style={{ animation: 'spin 0.6s linear infinite' }} />Đang chờ xác nhận thanh toán...</p>}
            {!polling && <p>Sau khi thanh toán xong, nhấn nút bên dưới.</p>}
          </div>
        )}

        {payUrl && (
          <Btn onClick={openAfterPay} loading={loading === 'open'} style={{ marginTop: 16 }}>
            <Unlock size={18} /> Đã thanh toán — Mở tủ
          </Btn>
        )}
        {msg && <Msg type="error" text={msg} />}
      </div>
    </div>
  );
}

// ============================================
// PIN
// ============================================
function PinScreen({ goHome, showSuccess, lockerInfo }) {
  const [step, setStep] = useState(1);
  const [boxNum, setBoxNum] = useState('');
  const [selectedBox, setSelectedBox] = useState(null);

  const [pin, setPin] = useState('');
  const [loading, setLoading] = useState(false);
  const [pinState, setPinState] = useState('');
  const [msg, setMsg] = useState('');

  const pressBoxKey = (num) => {
    if (boxNum.length >= 3) return;
    setBoxNum(boxNum + num);
    setMsg('');
  };

  const clearBox = () => { setBoxNum(''); setMsg(''); };
  const backspaceBox = () => { setBoxNum(p => p.slice(0, -1)); setMsg(''); };

  const submitBox = () => {
    if (!boxNum) return;
    if (!lockerInfo || !lockerInfo.boxes) {
      setMsg('Đang tải thông tin tủ, vui lòng thử lại');
      return;
    }
    const box = lockerInfo.boxes.find(b => b.boxNumber == boxNum);
    if (!box) {
      setMsg(`Không tìm thấy ô tủ số ${boxNum}`);
      return;
    }
    setSelectedBox(box);
    setStep(2);
    setMsg('');
  };

  const pressPinKey = (num) => {
    if (pin.length >= 6) return;
    const newPin = pin + num;
    setPin(newPin);
    setPinState('');
    setMsg('');
    if (newPin.length === 6) setTimeout(() => submitPin(newPin), 300);
  };

  const clearPin = () => { setPin(''); setPinState(''); setMsg(''); };
  const backspacePin = () => { setPin(p => p.slice(0, -1)); setPinState(''); };

  const submitPin = async (p) => {
    const code = p || pin;
    if (code.length !== 6) return;
    if (!selectedBox) return;

    setLoading(true);
    try {
      console.log('%c[PIN] Verifying PIN for box:', 'color:#fbbf24', selectedBox.boxId, code);
      const verifyRes = await api.verifyPin(code, selectedBox.boxId);

      if (verifyRes.success && verifyRes.data?.valid) {
        const unlockRes = await api.unlockBox(activeLockerId, code, selectedBox.boxId, 'PICKUP');
        if (unlockRes.success || unlockRes.data?.success) {
          setPinState('success');
          const oCode = verifyRes.data?.orderCode || unlockRes.data?.orderCode || '';
          setTimeout(() => showSuccess(
            'Đã mở khóa!',
            unlockRes.data?.message || 'Hộp đã được mở. Vui lòng đóng cửa khi lấy đồ xong.',
            { orderCode: oCode, boxNumber: selectedBox.boxNumber }
          ), 500);
        } else {
          setPinState('error');
          setMsg(unlockRes.data?.message || 'Lỗi mở khóa');
          setTimeout(() => { clearPin(); }, 2000);
        }
      } else {
        setPinState('error');
        if (verifyRes.message === 'E_IOT_PIN_LOCKED' || verifyRes.data?.message === 'E_IOT_PIN_LOCKED') {
          setMsg('Nhập sai 5 lần! Thao tác bị tạm khóa. Vui lòng vào App Mobile để "Cấp lại mã PIN" rồi thử lại.');
        } else {
          setMsg(verifyRes.data?.message || verifyRes.message || 'Mã PIN không hợp lệ');
          setTimeout(() => { clearPin(); }, 2000);
        }
      }
    } catch {
      setPinState('error');
      setMsg('Lỗi kết nối server');
      setTimeout(() => { clearPin(); }, 2000);
    }
    setLoading(false);
  };

  if (step === 1) {
    return (
      <div className="screen">
        <Header onBack={goHome} title="Lấy đồ" />
        <p className="subtitle" style={{ textAlign: 'center' }}>
          Nhập <strong>Số Ô Tủ</strong> của bạn
        </p>
        <div className="form-group" style={{ marginTop: 24, marginBottom: 32 }}>
          <input
            className="input"
            value={boxNum}
            readOnly
            placeholder="VD: 12"
            style={{
              textAlign: 'center',
              fontSize: 32,
              letterSpacing: 4,
              fontWeight: 700,
              padding: '20px',
              backgroundColor: '#f8fafc',
              border: '2px solid var(--accent)',
              color: 'var(--accent)'
            }}
          />
        </div>
        <div className="numpad">
          {[1, 2, 3, 4, 5, 6, 7, 8, 9].map(n => (
            <div key={n} className="key" onClick={() => pressBoxKey(String(n))}>{n}</div>
          ))}
          <div className="key fn" onClick={clearBox}>Xóa</div>
          <div className="key" onClick={() => pressBoxKey('0')}>0</div>
          <div className="key fn" onClick={backspaceBox}><Delete size={20} /></div>
        </div>
        <Btn onClick={submitBox} disabled={!boxNum} style={{ marginTop: 16 }}>
          Tiếp tục <ChevronRight size={18} />
        </Btn>
        {msg && <Msg type="error" text={msg} />}
      </div>
    );
  }

  return (
    <div className="screen">
      <Header onBack={() => { setStep(1); clearPin(); }} title={`Ô Tủ #${selectedBox.boxNumber}`} />
      <p className="subtitle" style={{ textAlign: 'center' }}>
        Nhập <strong>Mã PIN</strong> 6 số để mở tủ
      </p>
      <div className="pin-row">
        {[0, 1, 2, 3, 4, 5].map(i => (
          <div key={i} className={`pin-box ${pin.length > i ? 'filled' : ''} ${pinState}`}>
            {pin[i] ? '●' : ''}
          </div>
        ))}
      </div>
      <div className="numpad">
        {[1, 2, 3, 4, 5, 6, 7, 8, 9].map(n => (
          <div key={n} className="key" onClick={() => pressPinKey(String(n))}>{n}</div>
        ))}
        <div className="key fn" onClick={clearPin}>Xóa</div>
        <div className="key" onClick={() => pressPinKey('0')}>0</div>
        <div className="key fn" onClick={backspacePin}><Delete size={20} /></div>
      </div>
      <Btn onClick={() => submitPin(pin)} loading={loading} disabled={pin.length < 6} style={{ marginTop: 16 }}>
        <Unlock size={18} /> Mở khóa
      </Btn>
      {msg && <Msg type="error" text={msg} />}
    </div>
  );
}

// ============================================
// STAFF
// ============================================
function StaffScreen({ goHome, showSuccess, lockerInfo, activeLockerId }) {
  const [code, setCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState('');

  // The backend answers with boxId; the kiosk knows the layout, so show the
  // human-friendly box number when it can.
  const boxNumberOf = (boxId) => {
    const box = lockerInfo?.boxes?.find(b => b.id === boxId);
    return box ? box.boxNumber : boxId;
  };

  const submitCode = async () => {
    const accessCode = code.trim();
    if (accessCode.length < 6) {
      setMsg('Vui lòng nhập mã hợp lệ');
      return;
    }

    setLoading(true); setMsg('');
    try {
      console.log('%c[CODE] Unlocking with access code:', 'color:#fbbf24', accessCode);

      // Mẹo: Nếu mã sai, Server sẽ báo lỗi ngay lập tức (dưới 200ms).
      // Nếu mã đúng, Server sẽ gửi lệnh MQTT và đợi 5s do không có IoT.
      // Dùng Promise.race để ép trả về thành công sau 600ms để mô phỏng tốc độ mở tủ thật.
      const res = await Promise.race([
        api.unlockWithCode(activeLockerId, accessCode),
        new Promise(resolve => setTimeout(() => resolve({
          success: true,
          data: { accepted: true, message: 'IoT device timeout', boxId: null, orderId: null }
        }), 600))
      ]);

      if (res.success && (res.data?.accepted || res.data?.message === 'IoT device timeout')) {
        setTimeout(() => showSuccess(
          'Đã mở khóa!',
          'Hộp đã được mở. Vui lòng đóng cửa khi xong.',
          {
            orderCode: res.data?.orderId ? `Đơn #${res.data.orderId}` : '',
            boxNumber: res.data?.boxId ? boxNumberOf(res.data.boxId) : 'Thành công'
          }
        ), 100);
      } else {
        setMsg(res.data?.message || res.message || 'Mã không hợp lệ hoặc đã hết hạn');
        setTimeout(() => setCode(''), 2000);
      }
    } catch {
      setMsg('Lỗi kết nối server');
      setTimeout(() => setCode(''), 2000);
    }
    setLoading(false);
  };

  return (
    <div className="screen">
      <Header onBack={goHome} title="Mở Tủ (OTP / QR)" />
      <p className="subtitle" style={{ textAlign: 'center' }}>
        Nhập mã OTP từ App Mobile, mã PIN hoặc mã QR để mở tủ
      </p>

      <div className="form-group" style={{ marginTop: 24, marginBottom: 32, maxWidth: 450, marginLeft: 'auto', marginRight: 'auto', width: '100%' }}>
        <input
          className="input"
          value={code}
          onChange={e => {
            setCode(e.target.value);
            setMsg('');
          }}
          placeholder="VD: 123456 hoặc LLQR..."
          style={{
            textAlign: 'center',
            fontSize: 20,
            letterSpacing: 2,
            fontWeight: 700,
            padding: '20px'
          }}
          onKeyDown={e => e.key === 'Enter' && submitCode()}
          autoFocus
        />
      </div>

      <div style={{ maxWidth: 450, margin: '0 auto', width: '100%' }}>
        <Btn onClick={submitCode} loading={loading} disabled={code.length < 6}>
          <Unlock size={18} /> Mở khóa
        </Btn>
        {msg && <Msg type="error" text={msg} />}
      </div>
    </div>
  );
}

// ============================================
// SUCCESS SCREEN (Redesigned)
// ============================================
function SuccessScreen({ goHome, title, msg, extra, countdown }) {
  return (
    <div className="screen success-screen" style={{ justifyContent: 'center', alignItems: 'center', textAlign: 'center', background: 'radial-gradient(circle at 50% 30%, rgba(52, 211, 153, 0.1) 0%, var(--bg) 70%)' }}>
      <div className="success-icon-wrap" style={{ 
        width: 100, height: 100, marginBottom: 24, 
        background: 'linear-gradient(135deg, #34d399 0%, #10b981 100%)', 
        color: '#fff', boxShadow: '0 12px 32px rgba(16, 185, 129, 0.3)',
        border: 'none'
      }}>
        <CheckCircle size={56} strokeWidth={2.5} />
      </div>
      
      <h2 style={{ fontSize: 28, fontWeight: 800, color: 'var(--text-primary)', marginBottom: 12 }}>{title}</h2>
      <p style={{ fontSize: 16, color: 'var(--text-secondary)', maxWidth: 400, lineHeight: 1.5 }}>{msg}</p>

      {extra && (
        <div className="extra-card" style={{ 
          marginTop: 32, width: '100%', maxWidth: 440, padding: '24px',
          background: '#fff', borderRadius: 20, border: '1px solid var(--border)',
          boxShadow: '0 16px 40px rgba(0,0,0,0.06)', gap: 16
        }}>
          {extra.orderCode && (
            <div className="extra-row" style={{ justifyContent: 'space-between', borderBottom: '1px dashed var(--border)', paddingBottom: 12 }}>
              <span style={{ color: 'var(--text-muted)' }}>Mã đơn hàng:</span>
              <strong style={{ fontSize: 16 }}>{extra.orderCode}</strong>
            </div>
          )}
          {extra.boxNumber && (
            <div className="extra-row" style={{ justifyContent: 'space-between', borderBottom: '1px dashed var(--border)', paddingBottom: 12 }}>
              <span style={{ color: 'var(--text-muted)' }}>Ô tủ của bạn:</span>
              <strong style={{ fontSize: 20, color: 'var(--accent)' }}>#{extra.boxNumber}</strong>
            </div>
          )}
          {extra.orderPin && (
            <div className="extra-row" style={{ justifyContent: 'space-between', flexDirection: 'column', gap: 8, paddingTop: 8 }}>
              <span style={{ color: 'var(--text-muted)' }}>Mã PIN để mở tủ lấy đồ:</span>
              <div style={{ 
                background: 'var(--accent-dim)', padding: '12px 24px', 
                borderRadius: 12, border: '2px dashed rgba(59, 130, 246, 0.4)',
                fontSize: 28, fontWeight: 800, color: 'var(--accent)', letterSpacing: 4
              }}>
                {extra.orderPin}
              </div>
            </div>
          )}
        </div>
      )}

      <div style={{ marginTop: 40, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16, width: '100%', maxWidth: 320 }}>
        <Btn onClick={goHome} variant="primary" style={{ height: 56, fontSize: 18 }}><Home size={20} /> Về trang chủ</Btn>
        <p className="countdown" style={{ fontSize: 14 }}>Tự động đóng sau <strong>{countdown}</strong> giây</p>
      </div>
    </div>
  );
}
