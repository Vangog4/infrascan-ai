/**
 * InfraScan AI — Website Visual Enhancements
 */
(() => {
	const BOT_URL = "https://t.me/infrascan_ai_bot";
	const FORM_URL = "/zaiavka-na-audit";

	const qs = (sel, ctx) => (ctx || document).querySelector(sel);
	const qsa = (sel, ctx) => Array.from((ctx || document).querySelectorAll(sel));
	const isMobile = () => window.matchMedia("(pointer: coarse)").matches;
	const isReduced = () =>
		window.matchMedia("(prefers-reduced-motion: reduce)").matches;

	/* ── 1. Scroll reveal ─────────────────────────────────────── */
	function initReveal() {
		const targets = qsa(
			".card, .s_features_grid > *, .s_three_columns .col, " +
				".s_pricing_table .col, .s_text_image, .s_image_text, " +
				".s_numbers_block .col, .s_call_to_action",
		);
		const io = new IntersectionObserver(
			(entries) => {
				entries.forEach((e) => {
					if (!e.isIntersecting) return;
					e.target.classList.add("is-visible");
					io.unobserve(e.target);
				});
			},
			{ threshold: 0.12, rootMargin: "0px 0px -48px 0px" },
		);

		targets.forEach((el, i) => {
			el.classList.add("is-reveal");
			el.style.transitionDelay = `${((i % 4) * 0.1).toFixed(1)}s`;
			io.observe(el);
		});
	}

	/* ── 2. Navbar scroll shadow ──────────────────────────────── */
	function initNavbar() {
		const header = qs("header#top");
		if (!header) return;
		window.addEventListener(
			"scroll",
			() => {
				if (window.scrollY > 60) {
					header.style.background = "rgba(255, 255, 255, 0.97)";
					header.style.boxShadow = "0 4px 30px rgba(0, 0, 0, 0.13)";
				} else {
					header.style.background = "rgba(255, 255, 255, 0.90)";
					header.style.boxShadow = "0 2px 24px rgba(0, 0, 0, 0.08)";
				}
			},
			{ passive: true },
		);
	}

	/* ── 3. Cursor thermal glow ───────────────────────────────── */
	function initCursorGlow() {
		if (isMobile() || isReduced()) return;
		const orb = document.createElement("div");
		orb.id = "is-cursor-orb";
		Object.assign(orb.style, {
			position: "fixed",
			width: "420px",
			height: "420px",
			borderRadius: "50%",
			pointerEvents: "none",
			zIndex: "8888",
			background:
				"radial-gradient(circle, rgba(255,107,53,0.07) 0%, rgba(76,201,240,0.03) 40%, transparent 68%)",
			transform: "translate(-50%, -50%)",
			willChange: "left, top",
			transition: "opacity 0.4s ease",
		});
		document.body.appendChild(orb);
		let cx = window.innerWidth / 2,
			cy = window.innerHeight / 2;
		let tx = cx,
			ty = cy;
		document.addEventListener(
			"mousemove",
			(e) => {
				tx = e.clientX;
				ty = e.clientY;
			},
			{ passive: true },
		);
		document.addEventListener("mouseleave", () => {
			orb.style.opacity = "0";
		});
		document.addEventListener("mouseenter", () => {
			orb.style.opacity = "1";
		});
		(function tick() {
			cx += (tx - cx) * 0.07;
			cy += (ty - cy) * 0.07;
			orb.style.left = `${cx}px`;
			orb.style.top = `${cy}px`;
			requestAnimationFrame(tick);
		})();
	}

	/* ── 4. Animated counters ─────────────────────────────────── */
	function initCounters() {
		const els = qsa("[data-count]");
		if (!els.length) return;
		const io = new IntersectionObserver(
			(entries) => {
				entries.forEach((entry) => {
					if (!entry.isIntersecting) return;
					const el = entry.target;
					const target = parseInt(el.dataset.count, 10) || 0;
					const dur = 1600,
						start = performance.now();
					(function update(now) {
						const t = Math.min((now - start) / dur, 1);
						el.textContent = Math.round(
							(1 - 2 ** (-10 * t)) * target,
						).toLocaleString("ru-RU");
						if (t < 1) requestAnimationFrame(update);
					})(start);
					io.unobserve(el);
				});
			},
			{ threshold: 0.6 },
		);
		els.forEach((el) => io.observe(el));
	}

	/* ── 5. Hero heading stagger ──────────────────────────────── */
	function initHeroStagger() {
		if (isReduced()) return;
		const hero = qs(".s_banner, .s_cover, .s_hero");
		if (!hero) return;
		// Exclude .btn: hero buttons have their own isCtaPulse animation via CSS;
		// mixing isFadeUp inline + isCtaPulse !important leaves opacity:0 forever.
		qsa("h1, h2, .lead", hero).forEach((el, i) => {
			el.style.cssText += `
        opacity: 0;
        transform: translateY(26px);
        animation: isFadeUp 0.8s ${(0.1 + i * 0.15).toFixed(2)}s cubic-bezier(0.4,0,0.2,1) both;
      `;
		});
	}

	/* ── 6. Ripple on primary buttons ────────────────────────── */
	function initButtonRipple() {
		qsa(".btn-primary").forEach((btn) => {
			btn.addEventListener("click", function (e) {
				const r = this.getBoundingClientRect();
				const dot = document.createElement("span");
				const size = Math.max(r.width, r.height) * 2;
				Object.assign(dot.style, {
					position: "absolute",
					width: `${size}px`,
					height: `${size}px`,
					borderRadius: "50%",
					background: "rgba(255,255,255,0.25)",
					top: `${e.clientY - r.top - size / 2}px`,
					left: `${e.clientX - r.left - size / 2}px`,
					transform: "scale(0)",
					animation: "isRipple 0.55s ease forwards",
					pointerEvents: "none",
				});
				if (!document.getElementById("is-ripple-kf")) {
					const s = document.createElement("style");
					s.id = "is-ripple-kf";
					s.textContent =
						"@keyframes isRipple{to{transform:scale(1);opacity:0}}";
					document.head.appendChild(s);
				}
				this.style.position = "relative";
				this.style.overflow = "hidden";
				this.style.userSelect = "none";
				this.appendChild(dot);
				setTimeout(() => dot.remove(), 600);
			});
		});
	}

	/* ── 7. Hero block: badge + clean up + buttons ────────────── */
	function initHeroFix() {
		const hero = qs(".s_cover, .s_banner, .s_hero");
		if (!hero) return;

		// Remove orphaned lone-punctuation paragraphs left by the editor
		qsa("p", hero).forEach((p) => {
			if (/^\s*[.··\s]*\s*$/.test(p.textContent.replace(/ /g, " "))) p.remove();
		});

		// Inject expertise badge above H1 (only once)
		const h1 = hero.querySelector("h1");
		if (h1 && !hero.querySelector(".is-hero-badge")) {
			const badge = document.createElement("div");
			badge.className = "is-hero-badge";
			badge.innerHTML = "&#9679;&nbsp;&nbsp;Тепловизионная диагностика зданий";
			h1.parentNode.insertBefore(badge, h1);
		}

		// Fix hero buttons by position: first → bot, second → form
		const btns = qsa("a.btn", hero);
		btns.forEach((btn, i) => {
			const strip = [
				"color",
				"background-color",
				"border-color",
				"border-width",
				"border-style",
			];
			if (i === 0) {
				btn.textContent = "📸 Анализ фото бесплатно";
				btn.href = BOT_URL;
				btn.target = "_blank";
				btn.rel = "noopener noreferrer";
				btn.className = "btn is-btn-primary-hero";
				strip.forEach((p) => btn.style.removeProperty(p));
			} else if (i === 1) {
				btn.textContent = "Вызвать инженера →";
				btn.href = FORM_URL;
				btn.removeAttribute("target");
				btn.className = "btn is-btn-secondary-hero";
				strip.forEach((p) => btn.style.removeProperty(p));
			}
		});
	}

	/* ── 8. Nav links + section anchors + CTA buttons ────────── */
	function initNavAndSections() {
		// Section anchor IDs
		const anchorMap = [
			[".s_three_columns", "services"],
			[".s_text_image", "cases"],
			[".s_key_benefits, .s_pricing_table", "pricing"],
			[".s_call_to_action", "contacts"],
		];
		anchorMap.forEach(([sel, id]) => {
			const el = qs(sel);
			if (el && !el.id) el.id = id;
		});

		// Navbar menu links
		const navLinkMap = [
			{ texts: ["Услуги", "Сервис"], href: "/#services" },
			{ texts: ["Кейсы", "Примеры"], href: "/#cases" },
			{ texts: ["Цены", "Тарифы"], href: "/#pricing" },
			{ texts: ["Контакты"], href: "/#contacts" },
			{ texts: ["Блог"], href: BOT_URL, target: "_blank" },
		];
		qsa("header#top .nav-link, header#top a.navbar-item").forEach((a) => {
			const text = a.textContent.trim();
			for (const rule of navLinkMap) {
				if (rule.texts.some((t) => text.includes(t))) {
					a.href = rule.href;
					if (rule.target) {
						a.target = rule.target;
						a.rel = "noopener noreferrer";
					} else {
						a.removeAttribute("target");
					}
					break;
				}
			}
		});

		// Rename "Блог" → "Telegram" in nav
		qsa("header#top .nav-link").forEach((a) => {
			if (a.textContent.trim() === "Блог") {
				a.textContent = "Telegram";
				a.href = BOT_URL;
				a.target = "_blank";
				a.rel = "noopener noreferrer";
			}
		});

		// Fix dead href="#" links → bot
		document.querySelectorAll('a[href="#"]').forEach((a) => {
			const text = a.textContent.trim().toLowerCase();
			if (
				text.includes("запис") ||
				text.includes("заказ") ||
				text.includes("начат") ||
				text.includes("попроб") ||
				text === ""
			) {
				a.href = BOT_URL;
				a.target = "_blank";
				a.rel = "noopener noreferrer";
			}
		});

		// Pricing / CTA section buttons → bot
		qsa(
			".s_key_benefits a.btn, .s_pricing_table a.btn, .s_call_to_action a.btn",
		).forEach((btn) => {
			const text = btn.textContent.trim();
			if (
				text.includes("Заказ") ||
				text.includes("Запис") ||
				text.includes("Получи")
			) {
				btn.textContent = "Записаться →";
				btn.href = BOT_URL;
				btn.target = "_blank";
				btn.rel = "noopener noreferrer";
			}
		});

		// "Аудит / Инженер" links without valid href → form
		qsa("a.btn").forEach((btn) => {
			const text = btn.textContent.trim();
			if (
				(text.includes("аудит") || text.includes("инженер")) &&
				(!btn.href ||
					btn.href.endsWith("/#") ||
					btn.getAttribute("href") === "#")
			) {
				btn.href = FORM_URL;
				btn.removeAttribute("target");
			}
		});
	}

	/* ── 9. SEO: image alt texts ──────────────────────────────── */
	function initImageAlts() {
		const altMap = [
			[
				/\/web\/image\/website\/\d+\/logo/,
				"ИнфраСкан — тепловизионная диагностика",
			],
			[/932/, "Тепловизионная диагностика жилой недвижимости"],
			[/934/, "Электроаудит — обнаружение перегрева контактов"],
			[/935/, "Диагностика тёплого пола тепловизором"],
			[/936/, "ИнфраСкан — профессиональная тепловизионная диагностика"],
			[/odoo_logo/, ""],
		];
		document.querySelectorAll("img").forEach((img) => {
			const src = img.getAttribute("src") || "";
			if (!img.alt || img.alt === "My Website") {
				for (const [pat, alt] of altMap) {
					if (pat.test(src)) {
						img.alt = alt;
						break;
					}
				}
			}
		});
	}

	/* ── Init ─────────────────────────────────────────────────── */
	function boot() {
		initReveal();
		initNavbar();
		initCursorGlow();
		initCounters();
		initHeroStagger();
		initButtonRipple();
		initHeroFix();
		initNavAndSections();
		initImageAlts();
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", boot);
	} else {
		boot();
	}
})();
