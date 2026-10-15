import "../styles/LandingPage.css";

const features = [
  {
    title: "Ghi âm & phiên âm trực tiếp",
    desc: "Ghi lại cuộc họp và nhận bản phiên âm theo thời gian thực. Không bỏ sót bất kỳ thông tin nào trong suốt buổi họp.",
  },
  {
    title: "Tải file ghi âm lên để phân tích",
    desc: "Upload file âm thanh có sẵn để hệ thống tự động tạo bản phiên âm và tóm tắt nội dung cuộc họp.",
  },
  {
    title: "Tóm tắt nội dung tự động",
    desc: "Hệ thống phân tích nội dung cuộc họp và trích xuất các điểm chính, quyết định và công việc cần làm.",
  },
  {
    title: "Lưu trữ và tra cứu lịch sử",
    desc: "Toàn bộ bản ghi và tóm tắt được lưu trữ an toàn, dễ dàng tra cứu và chia sẻ sau mỗi cuộc họp.",
  },
];

const steps = [
  { num: "1", title: "Tạo tài khoản", desc: "Đăng ký nhanh chóng và miễn phí." },
  { num: "2", title: "Bắt đầu hoặc tải file", desc: "Ghi âm trực tiếp hoặc tải lên file có sẵn." },
  { num: "3", title: "Nhận kết quả", desc: "Hệ thống tự động tạo bản phiên âm và tóm tắt." },
  { num: "4", title: "Lưu & Xuất", desc: "Xem lại trong lịch sử hoặc tải xuống kết quả." },
];

export default function LandingPage({ onLogin, onRegister }) {
  return (
    <div className="lp-root">
      {/* ── Header ─── */}
      <header className="lp-header">
        <div className="lp-header-inner">
          <div className="lp-logo">
            <svg className="lp-logo-svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
              <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
              <line x1="12" y1="19" x2="12" y2="22" />
            </svg>
            <span className="lp-logo-text">AI Meeting Note</span>
          </div>
          <nav className="lp-nav-links">
            <a href="#features" className="lp-nav-link">Tính năng</a>
            <a href="#guide" className="lp-nav-link">Hướng dẫn</a>
          </nav>
          <div className="lp-header-actions">
            <button className="lp-btn-ghost" onClick={onLogin}>Đăng nhập</button>
            <button className="lp-btn-primary" onClick={onRegister}>Đăng ký miễn phí</button>
          </div>
        </div>
      </header>

      {/* ── Hero ─── */}
      <section className="lp-hero">
        <div className="lp-hero-content">
          <h1 className="lp-hero-title">
            Tóm tắt cuộc họp<br />thông minh với AI
          </h1>
          <p className="lp-hero-desc">
            AI Meeting Note tự động phiên âm và tóm tắt nội dung cuộc họp của bạn.
            Ghi âm trực tiếp hoặc tải lên file — kết quả sẵn sàng trong vài phút.
          </p>
          <div className="lp-hero-cta">
            <button className="lp-btn-hero" onClick={onRegister}>Bắt đầu miễn phí</button>
          </div>
        </div>

        {/* Hình ảnh cuộc họp */}
        <div className="lp-hero-visual">
          <div className="lp-hero-image-card">
            <img
              src="/meeting-hero.jpg"
              alt="Cuộc họp thông minh"
              className="lp-hero-img"
            />
          </div>
        </div>
      </section>

      {/* ── Features ─── */}
      <section id="features" className="lp-section lp-features-section">
        <div className="lp-section-inner">
          <div className="lp-section-header">
            <h2 className="lp-section-title">Tính năng chính</h2>
            <p className="lp-section-desc">
              Đầy đủ công cụ để ghi chép và tổng hợp nội dung cuộc họp một cách hiệu quả.
            </p>
          </div>
          <div className="lp-features-grid">
            {features.map((f, i) => (
              <div key={i} className="lp-feature-card">
                <h3 className="lp-feature-title">{f.title}</h3>
                <p className="lp-feature-desc">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Hướng dẫn ─── */}
      <section id="guide" className="lp-section lp-how-section">
        <div className="lp-section-inner">
          <div className="lp-section-header">
            <h2 className="lp-section-title">Hướng dẫn sử dụng</h2>
            <p className="lp-section-desc">Bắt đầu chỉ trong vài bước đơn giản.</p>
          </div>
          <div className="lp-steps-grid">
            {steps.map((s, i) => (
              <div key={i} className="lp-step-card">
                <div className="lp-step-num">{s.num}</div>
                <h3 className="lp-step-title">{s.title}</h3>
                <p className="lp-step-desc">{s.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA ─── */}
      <section className="lp-cta-section">
        <div className="lp-cta-content">
          <h2 className="lp-cta-title">Sẵn sàng bắt đầu?</h2>
          <p className="lp-cta-desc">
            Tạo tài khoản miễn phí và trải nghiệm ngay hôm nay.
          </p>
          <div className="lp-cta-btns">
            <button className="lp-btn-hero" onClick={onRegister}>Đăng ký miễn phí</button>
            <button className="lp-btn-hero-outline" onClick={onLogin}>Đã có tài khoản? Đăng nhập</button>
          </div>
        </div>
      </section>

      {/* ── Footer ─── */}
      <footer className="lp-footer">
        <div className="lp-footer-inner">
          <div className="lp-footer-brand">
            <svg className="lp-logo-svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
              <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
              <line x1="12" y1="19" x2="12" y2="22" />
            </svg>
            <span className="lp-footer-brand-name">AI Meeting Note</span>
          </div>
          <p className="lp-footer-copy">
            © 2026 AI Meeting Note — Đồ án HTTM
          </p>
        </div>
      </footer>
    </div>
  );
}
