    (() => {
      const tg = window.Telegram && window.Telegram.WebApp;
      const app = document.getElementById('app');
      let wines = [];
      let screen = { name: 'home' };
      const storageKey = 'dacha-cart-v2';
      let draft = { cart: {}, requestId: null, fingerprint: null };
      try { draft = { ...draft, ...JSON.parse(localStorage.getItem(storageKey) || '{}') }; } catch (_) {}
      if (typeof draft.fingerprint !== 'string' || !/^[a-f0-9]{64}$/.test(draft.fingerprint)) draft.requestId = draft.fingerprint = null;
      if (!draft.cart || typeof draft.cart !== 'object' || Array.isArray(draft.cart)) draft.cart = {};
      let formDraft = {};
      let sending = false;
      const money = value => new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(value) + ' ₽';
      const priceLabel = wine => wine.price ? money(wine.price) : 'Цена уточняется';
      const saveCart = () => { try { localStorage.setItem(storageKey, JSON.stringify(draft)); } catch (_) {} };
      const cartItems = () => wines.filter(wine => draft.cart[wine.sku]).map(wine => ({ wine, quantity: draft.cart[wine.sku] }));
      const cartCount = () => cartItems().reduce((sum, item) => sum + item.quantity, 0);
      const cartTotal = () => cartItems().reduce((sum, item) => sum + item.quantity * item.wine.price, 0);
      const unknownPrices = () => cartItems().some(item => !item.wine.price);
      const quantityControl = wine => `<div class="quantity"><button type="button" data-quantity="${esc(wine.sku)}" data-delta="-1" aria-label="Уменьшить количество">−</button><span aria-live="polite">${draft.cart[wine.sku] || 0} шт.</span><button type="button" data-quantity="${esc(wine.sku)}" data-delta="1" aria-label="Увеличить количество" ${draft.cart[wine.sku] >= 99 || !wine.in_stock ? 'disabled' : ''}>+</button></div>`;
      function back() {
        if (screen.name === 'wine') screen = { name: 'category', category: wines.find(wine => wine.id === screen.id)?.category || '' };
        else if (screen.name === 'checkout') screen = { name: 'cart' };
        else screen = { name: 'home' };
        render();
        window.scrollTo(0, 0);
      }
      function changeQuantity(sku, delta) {
        const wine = wines.find(item => item.sku === sku);
        if (!wine || (delta > 0 && !wine.in_stock)) return;
        const qty = Math.min(99, Math.max(0, (draft.cart[sku] || 0) + delta));
        if (qty) draft.cart[sku] = qty; else delete draft.cart[sku];
        draft.requestId = draft.fingerprint = null;
        saveCart();
      }
      function renderCart() {
        const lines = cartItems().map(({ wine, quantity }) => `<article class="cart-item"><img src="${esc(wine.image)}" alt=""><div><h2>${esc(wine.name)}</h2><span class="price">${wine.price ? money(wine.price * quantity) : 'Цена уточняется'}</span>${!wine.in_stock ? '<p class="stock-note">Закончилось — удалите из корзины.</p>' : ''}${quantityControl(wine)}</div></article>`).join('');
        const blocked = cartItems().some(({ wine }) => !wine.in_stock);
        app.innerHTML = `<header class="masthead"><span>Дача Сердюка</span><span class="place">Ваш выбор</span></header><button class="back" data-back>← В каталог</button><h1 class="view-title">Корзина</h1>${lines || '<p class="state-message">Здесь пока пусто. Выберите напиток в каталоге.</p>'}${lines ? `<section class="cart-summary"><div class="cart-total"><span>${unknownPrices() ? 'Известные цены' : 'Итого'}</span><span>${money(cartTotal())}</span></div><p class="small">${unknownPrices() ? 'Цены отдельных позиций уточнит менеджер. ' : ''}Доставка согласуется отдельно. Онлайн-оплаты нет.</p><button class="primary" data-checkout ${blocked ? 'disabled' : ''}>Оформить заявку</button><button class="text-link" data-clear>Очистить корзину</button></section>` : ''}`;
      }
      function renderCheckout() {
        if (!cartCount()) { screen = { name: 'cart' }; renderCart(); return; }
        app.innerHTML = `<header class="masthead"><span>Дача Сердюка</span><span class="place">Заявка без оплаты</span></header><button class="back" data-back>← Корзина</button><h1 class="view-title">Детали заказа</h1><p class="view-description">${cartCount()} шт. · ${unknownPrices() ? 'известные цены: ' : ''}${money(cartTotal())}</p><form id="checkout-form" class="checkout-form"><label for="full-name">Как к вам обращаться</label><input id="full-name" name="full_name" autocomplete="name" minlength="2" maxlength="80" required value="${esc(formDraft.full_name || '')}"><label for="phone">Телефон для связи</label><input id="phone" name="phone" type="tel" autocomplete="tel" minlength="7" maxlength="20" required value="${esc(formDraft.phone || '')}"><label for="address">Город, адрес или пожелания к получению</label><textarea id="address" name="address" autocomplete="street-address" minlength="5" maxlength="250" required>${esc(formDraft.address || '')}</textarea><p class="small">Контакты и состав заявки будут доступны менеджеру и сотрудникам магазина с разрешённым доступом.</p><p class="small">${unknownPrices() ? 'Цены отдельных позиций и ' : ''}Доставку согласуем с менеджером до подтверждения.</p><p id="form-error" class="form-error" role="alert"></p><button type="submit" class="primary">Отправить заявку</button></form>${draft.requestId ? '<p class="notice">Эта заявка уже передавалась боту. Проверьте результат в чате. Повторная отправка с тем же составом и контактами не создаст дубль.</p><button class="text-link" data-new-order>Создать ещё один такой заказ</button>' : ''}`;
      }

      const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
      const excerpt = text => {
        const sentence = String(text || '').split(/(?<=[.!?])\s+/)[0];
        return sentence.length > 125 ? sentence.slice(0, 122).trimEnd() + '…' : sentence;
      };
      const categories = () => [...new Set(wines.map(wine => wine.category))];
      const backButton = () => {
        if (!tg || !tg.BackButton) return;
        if (screen.name === 'home') tg.BackButton.hide();
        else tg.BackButton.show();
      };
      function goHome() { screen = { name: 'home' }; render(); }
      function render() {
        document.getElementById('cart-dock')?.remove();
        if (screen.name === 'cart') { renderCart(); backButton(); return; }
        if (screen.name === 'checkout') { renderCheckout(); backButton(); return; }
        if (tg) { tg.ready(); tg.expand(); tg.MainButton?.hide(); }
        backButton();
        if (screen.name === 'home') {
          const rows = categories().map(category => {
            const count = wines.filter(wine => wine.category === category).length;
            return `<button class="category-row" data-category="${esc(category)}"><span class="category-name">${esc(category)}</span><span class="category-meta">${count} ${count === 1 ? 'вино' : count < 5 ? 'вина' : 'вин'} <span class="category-arrow">↗</span></span></button>`;
          }).join('');
          app.innerHTML = `<header class="masthead"><span>Дача Сердюка</span><span class="place">Долина Дона · с 2003 года</span></header>
            <section class="hero"><p class="eyebrow">Безалкогольная коллекция · 0,16%</p><h1>Вино<br>с берегов<br>Дона.</h1><p class="hero-copy">Небольшое семейное хозяйство. Виноград, ручной труд и вино без спешки.</p><div class="hero-note">Усть-Донецкий район · хутор Каныгин</div></section>
            <section aria-labelledby="wines-title"><div class="section-head"><h2 id="wines-title">Винная карта</h2><span>${wines.length} вин</span></div><div class="category-list">${rows}</div></section>
            <section class="about-teaser"><p class="eyebrow">О хозяйстве</p><h2>Семейное дело у Дона</h2><p>Выращиваем местные и грузинские сорта и работаем с вином вручную, следуя характеру винограда и места.</p><button class="text-link" data-about>История винодельни <span aria-hidden="true">↗</span></button></section>
            <footer class="footnote">Винная карта и рассказы о хозяйстве «Дача Сердюка»</footer>`;
        } else if (screen.name === 'category') {
          const products = wines.filter(wine => wine.category === screen.category);
          const rows = products.map(wine => `<button class="wine-row" data-wine="${wine.id}"><img class="wine-thumb" src="${esc(wine.image)}" alt="" loading="lazy"><span class="wine-card-copy"><span class="eyebrow">${esc(wine.category)}</span><span class="wine-name">${esc(wine.name)}</span><span class="wine-blurb">${esc(excerpt(wine.aroma + ' ' + wine.taste))}</span><span class="price">${priceLabel(wine)}</span>${!wine.in_stock ? '<span class="stock-note">Закончилось</span>' : ''}</span><span class="row-arrow" aria-hidden="true">↗</span></button>`).join('');
          app.innerHTML = `<header class="masthead"><span>Дача Сердюка</span><span class="place">Винная карта</span></header><button class="back" data-back>← Все категории</button><h1 class="view-title">${esc(screen.category)}</h1><p class="view-description">${products.length} ${products.length === 1 ? 'вино' : products.length < 5 ? 'вина' : 'вин'} из нашей винной карты</p><div class="wine-list">${rows}</div>`;
        } else if (screen.name === 'wine') {
          const wine = wines.find(item => item.id === screen.id);
          if (!wine) { goHome(); return; }
          app.innerHTML = `<header class="masthead"><span>Дача Сердюка</span><span class="place">${esc(wine.category)}</span></header><button class="back" data-back>← ${esc(wine.category)}</button><section class="detail-top"><img class="detail-image" src="${esc(wine.image)}" alt="Бутылка вина «${esc(wine.name)}»"><div class="detail-heading"><p class="eyebrow">${esc(wine.category)}</p><h1>${esc(wine.name)}</h1><p class="grape">${esc(wine.variety)}</p><p class="stock-note">Безалкогольное · 0,16%</p><span class="price">${priceLabel(wine)}</span><p class="detail-note">${esc(wine.aging)}</p></div></section><div class="purchase">${draft.cart[wine.sku] ? quantityControl(wine) : `<button class="primary" data-quantity="${esc(wine.sku)}" data-delta="1" ${!wine.in_stock ? 'disabled' : ''}>${wine.in_stock ? 'Добавить в корзину' : 'Закончилось'}</button>`}</div><section class="notes"><article class="note"><h2>Ароматика</h2><p>${esc(wine.aroma)}</p></article><article class="note"><h2>Вкус</h2><p>${esc(wine.taste)}</p></article><article class="note"><h2>К столу</h2><p>${esc(wine.pairing)}</p></article></section><footer class="footnote">Описание по материалам винодельни «Дача Сердюка»</footer>`;
        } else if (screen.name === 'about') {
          app.innerHTML = `<header class="masthead"><span>Дача Сердюка</span><span class="place">Долина Дона</span></header><button class="back" data-back>← На главную</button><section class="about-page"><p class="eyebrow">Наша история</p><h1>Семейная винодельня на Дону</h1><p class="about-lead">«Дача Сердюка» основана в 2003 году. Это семейное хозяйство, где отец и три сына вместе занимаются виноградом и вином.</p><article class="about-section"><h2>Место</h2><p>Виноградники находятся в Усть-Донецком районе, у хутора Каныгин. Их заложили в 2014 году. Два с половиной гектара песчаных и глинистых почв.</p><ul class="facts-list"><li>Сибирьковый</li><li>Красностоп Золотовский</li><li>Саперави</li><li>Каберне Совиньон</li><li>Ркацители</li></ul></article><article class="about-section"><h2>Работа в погребе</h2><p>Семейное производство, ручной труд и спонтанное брожение на диких дрожжах для красных и оранжевых вин. Вина не осветляют и не фильтруют; в презентации винодельни также заявлено, что консерванты, включая диоксид серы, не добавляются.</p></article><article class="about-section"><h2>Забота о степи</h2><p>По материалам презентации, 10 рублей с каждой бутылки направляются в проект «Живая природа степи».</p></article></section><footer class="footnote">Факты и описание — из презентации винодельни «Дача Сердюка».</footer>`;
        }
        const dock = document.createElement('nav');
        dock.id = 'cart-dock';
        dock.className = 'cart-dock';
        dock.innerHTML = `<button class="primary" data-cart>Корзина${cartCount() ? ` · ${cartCount()} шт. · ${money(cartTotal())}` : ''}</button>`;
        app.appendChild(dock);
      }
      app.addEventListener('click', event => {
        const button = event.target.closest('button');
        if (!button || button.disabled || (button.closest('form') && button.type === 'submit')) return;
        const scroll = window.scrollY;
        if (button.dataset.quantity) {
          changeQuantity(button.dataset.quantity, Number(button.dataset.delta));
          render(); window.scrollTo(0, scroll); return;
        }
        if (button.dataset.category) screen = { name: 'category', category: button.dataset.category };
        else if (button.dataset.wine) screen = { name: 'wine', id: Number(button.dataset.wine) };
        else if (button.hasAttribute('data-about')) screen = { name: 'about' };
        else if (button.hasAttribute('data-cart')) screen = { name: 'cart' };
        else if (button.hasAttribute('data-checkout')) screen = { name: 'checkout' };
        else if (button.hasAttribute('data-back')) { back(); return; }
        else if (button.hasAttribute('data-clear')) { draft = { cart: {}, requestId: null, fingerprint: null }; saveCart(); }
        else if (button.hasAttribute('data-new-order')) { draft.requestId = draft.fingerprint = null; saveCart(); }
        render(); window.scrollTo(0, 0);
      });
      app.addEventListener('input', event => {
        if (event.target.closest('#checkout-form')) formDraft = Object.fromEntries(new FormData(document.getElementById('checkout-form')));
      });
      app.addEventListener('submit', async event => {
        if (event.target.id !== 'checkout-form') return;
        event.preventDefault();
        if (sending) return;
        const error = document.getElementById('form-error');
        formDraft = Object.fromEntries(new FormData(event.target));
        const customer = Object.fromEntries(Object.entries(formDraft).map(([key, value]) => [key, value.trim()]));
        if (customer.full_name.length < 2 || !/^[+\d][\d\s\-()]{6,19}$/.test(customer.phone) || customer.address.length < 5) {
          error.textContent = 'Проверьте имя, телефон и адрес.'; return;
        }
        if (!cartCount() || cartItems().some(({ wine }) => !wine.in_stock)) { error.textContent = 'Проверьте наличие товаров в корзине.'; return; }
        if (!tg || tg.platform === 'unknown' || tg.initDataUnsafe?.query_id) {
          error.textContent = 'Откройте личный чат с ботом, отправьте /start и нажмите «Открыть магазин» под полем ввода.'; return;
        }
        const items = cartItems().map(({ wine, quantity }) => ({ sku: wine.sku, quantity, price: wine.price }));
        if (!window.crypto?.subtle) { error.textContent = 'Для отправки требуется защищённое HTTPS-соединение.'; return; }
        sending = true;
        const digest = await window.crypto.subtle.digest('SHA-256', new TextEncoder().encode(JSON.stringify({ items, customer })));
        const fingerprint = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
        if (!draft.requestId || draft.fingerprint !== fingerprint) {
          draft.requestId = window.crypto?.randomUUID?.() || Date.now().toString(36) + Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2);
          draft.fingerprint = fingerprint;
        }
        const payload = JSON.stringify({ version: 2, request_id: draft.requestId, items, customer });
        if (new TextEncoder().encode(payload).length > 4096) { sending = false; error.textContent = 'Сократите адрес или комментарий.'; return; }
        saveCart();
        try {
          sending = true;
          event.target.querySelector('[type="submit"]').disabled = true;
          tg.sendData(payload);
          error.textContent = 'Заявка передана Telegram. Результат появится в чате бота.';
        } catch (_) {
          sending = false;
          event.target.querySelector('[type="submit"]').disabled = false;
          error.textContent = 'Не удалось передать заявку. Попробуйте ещё раз.';
        }
      });
      if (tg && tg.BackButton) tg.BackButton.onClick(back);
      fetch('./catalog.json?v=' + encodeURIComponent(new URLSearchParams(location.search).get('v') || 'checkout-1'), { cache: 'no-store' }).then(response => {
        if (!response.ok) throw new Error('catalog unavailable');
        return response.json();
      }).then(data => {
        if (!Array.isArray(data) || !data.length) throw new Error('catalog empty');
        wines = data;
        for (const [sku, qty] of Object.entries(draft.cart)) {
          if (!wines.some(wine => wine.sku === sku) || !Number.isInteger(qty) || qty < 1 || qty > 99) delete draft.cart[sku];
        }
        saveCart();
        render();
      }).catch(() => {
        app.innerHTML = '<p class="state-message">Не удалось загрузить винную карту. Проверьте подключение и откройте страницу ещё раз.</p>';
      });
    })();
