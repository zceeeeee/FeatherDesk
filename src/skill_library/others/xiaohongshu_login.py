"""Xiaohongshu SMS login preparation.

The skill opens the login page, fills a phone number, accepts the agreement,
and requests an SMS code. The final code entry remains manual.
"""

try:
    from src.layer_2 import controls as _controls
except Exception:
    _controls = None


DEFAULT_LOGIN_URL = "https://www.xiaohongshu.com/login"


def _default_log(message):
    print(f"[LOG] {message}")


def _safe_call(func, default, *args):
    try:
        return func(*args)
    except Exception:
        return default


def _resolve_log(log_fn):
    if log_fn is not None:
        return log_fn
    try:
        return log
    except NameError:
        return _default_log


def _normalize_phone_number(phone_number):
    digits = ""
    for char in str(phone_number):
        if "0" <= char <= "9":
            digits += char

    if len(digits) == 13 and digits[:2] == "86":
        digits = digits[2:]

    if len(digits) != 11 or digits[0] != "1" or digits[1] < "3" or digits[1] > "9":
        raise ValueError("Xiaohongshu login requires a valid 11-digit phone number")

    return digits


def _js_string(value):
    text = str(value)
    text = text.replace("\\", "\\\\")
    text = text.replace('"', '\\"')
    text = text.replace("\n", "\\n")
    text = text.replace("\r", "\\r")
    return '"' + text + '"'


def _run_js_dict(run_js_fn, code):
    try:
        result = run_js_fn(code)
    except Exception as exc:
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"}

    if isinstance(result, dict):
        return result
    return {"success": bool(result), "result": result}


def _detect_blocked(get_url_fn, get_text_fn):
    url = str(_safe_call(get_url_fn, "") or "")
    text = str(_safe_call(get_text_fn, "") or "")

    if (
        "website-login/error" in url
        or "安全限制" in text
        or "IP存在风险" in text
        or "存在风险" in text
    ):
        return {
            "success": False,
            "requires_network_change": True,
            "error": "Xiaohongshu returned a security restriction page",
            "url": url,
        }

    return None


def _open_login_panel(run_js_fn):
    return _run_js_dict(
        run_js_fn,
        """
(() => {
  const visible = (el) => {
    const style = window.getComputedStyle(el);
    return style && style.visibility !== 'hidden' && style.display !== 'none' &&
      (el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  };
  const hasPhoneInput = Array.from(document.querySelectorAll('input')).some((el) => {
    const text = [
      el.placeholder || '',
      el.type || '',
      el.name || '',
      el.id || '',
      el.autocomplete || ''
    ].join(' ').toLowerCase();
    return visible(el) && /(手机|手机号|phone|mobile|tel)/i.test(text);
  });
  if (hasPhoneInput) {
    return {success: true, already_open: true};
  }

  const candidates = Array.from(
    document.querySelectorAll('button,[role="button"],a,div,span')
  ).filter(visible).filter((el) => {
    const text = (el.innerText || el.textContent || '').trim().replace(/\\s+/g, '');
    const lower = text.toLowerCase();
    return text === '登录' || text === '登陆' || lower === 'login';
  });

  if (!candidates.length) {
    return {success: true, clicked: false};
  }

  candidates[0].click();
  return {
    success: true,
    clicked: true,
    text: (candidates[0].innerText || candidates[0].textContent || '').trim()
  };
})()
""",
    )


def _fill_phone(run_js_fn, phone_number):
    return _run_js_dict(
        run_js_fn,
        """
(() => {
  const phone = PHONE_NUMBER;
  const visible = (el) => {
    const style = window.getComputedStyle(el);
    return style && style.visibility !== 'hidden' && style.display !== 'none' &&
      (el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  };
  const textOf = (el) => [
    el.placeholder || '',
    el.type || '',
    el.name || '',
    el.id || '',
    el.autocomplete || '',
    el.inputMode || ''
  ].join(' ').toLowerCase();
  const denied = (text) => /(验证码|code|密码|password|邮箱|email|请选择|select)/i.test(text);
  const inputs = Array.from(document.querySelectorAll('input')).filter(visible);
  let target = inputs.find((el) => {
    const text = textOf(el);
    return /(手机|手机号|phone|mobile|tel)/i.test(text) && !denied(text);
  });
  if (!target) {
    target = inputs.find((el) => {
      const text = textOf(el);
      const type = (el.type || '').toLowerCase();
      return !denied(text) && (!type || type === 'text' || type === 'tel' || type === 'number');
    });
  }
  if (!target) {
    return {success: false, error: 'Phone input not found'};
  }

  target.focus();
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
  setter.call(target, phone);
  target.dispatchEvent(new Event('input', {bubbles: true}));
  target.dispatchEvent(new Event('change', {bubbles: true}));
  return {
    success: true,
    placeholder: target.placeholder || '',
    name: target.name || '',
    type: target.type || ''
  };
})()
""".replace("PHONE_NUMBER", _js_string(phone_number)),
    )


def _accept_agreement(run_js_fn):
    return _run_js_dict(
        run_js_fn,
        """
(() => {
  const visible = (el) => {
    const style = window.getComputedStyle(el);
    return style && style.visibility !== 'hidden' && style.display !== 'none' &&
      (el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  };
  const normalize = (text) => (text || '').trim().replace(/\\s+/g, '');
  const agreementText = (text) => {
    const normalized = normalize(text);
    return /用户协议/.test(normalized) &&
      /隐私政策/.test(normalized) &&
      (/我已阅读并同意|我已阅读|同意|儿童|青少年|登录即同意/.test(normalized));
  };
  const nearAgreement = (el) => {
    let node = el;
    for (let i = 0; i < 6 && node; i += 1) {
      if (agreementText(node.innerText || node.textContent || '')) {
        return true;
      }
      node = node.parentElement;
    }
    return false;
  };
  const dispatchCheckboxEvents = (el) => {
    el.dispatchEvent(new Event('input', {bubbles: true}));
    el.dispatchEvent(new Event('change', {bubbles: true}));
  };
  const clickCheckbox = (el) => {
    if (!el) {
      return false;
    }
    try {
      el.scrollIntoView({block: 'center', inline: 'center'});
    } catch (error) {}
    if (el.type === 'checkbox') {
      if (!el.checked) {
        el.click();
      }
      if (!el.checked) {
        const descriptor = Object.getOwnPropertyDescriptor(
          window.HTMLInputElement.prototype,
          'checked'
        );
        if (descriptor && descriptor.set) {
          descriptor.set.call(el, true);
        } else {
          el.checked = true;
        }
        dispatchCheckboxEvents(el);
      }
      return !!el.checked;
    }
    el.click();
    return true;
  };

  const checkboxes = Array.from(document.querySelectorAll('input[type="checkbox"]'));
  let target = checkboxes.find((el) => !el.checked && nearAgreement(el));
  if (!target) {
    target = checkboxes.find((el) => !el.checked && visible(el));
  }
  if (target) {
    const checked = clickCheckbox(target);
    return {success: true, checked, method: 'checkbox'};
  }

  const roleCheckboxes = Array.from(
    document.querySelectorAll('[role="checkbox"],[aria-checked]')
  ).filter((el) => visible(el) && el.getAttribute('aria-checked') !== 'true');
  target = roleCheckboxes.find(nearAgreement) || roleCheckboxes[0];
  if (target) {
    clickCheckbox(target);
    return {success: true, method: 'role_checkbox'};
  }

  const textTargets = [];
  for (const el of Array.from(document.querySelectorAll('label,div,span,p'))) {
    if (!visible(el) || !agreementText(el.innerText || el.textContent || '')) {
      continue;
    }
    let node = el;
    for (let depth = 0; depth < 5 && node; depth += 1) {
      if (visible(node) && agreementText(node.innerText || node.textContent || '')) {
        const rect = node.getBoundingClientRect();
        const area = rect.width * rect.height;
        const hasAgreementChildren = node.children.length > 0 ||
          Boolean(node.querySelector('a,input,[role="checkbox"],[aria-checked]'));
        if (
          hasAgreementChildren &&
          area > 0 &&
          area < window.innerWidth * window.innerHeight * 0.6
        ) {
          textTargets.push({el: node, rect, area});
        }
      }
      node = node.parentElement;
    }
  }

  textTargets.sort((a, b) => a.area - b.area);
  for (const item of textTargets) {
    const checkbox = Array.from(
      item.el.querySelectorAll('input[type="checkbox"],[role="checkbox"],[aria-checked]')
    ).find((el) => visible(el) || el.type === 'checkbox');
    if (checkbox) {
      clickCheckbox(checkbox);
      return {success: true, method: 'agreement_container_checkbox'};
    }

    const y = Math.min(Math.max(item.rect.top + item.rect.height / 2, 0), window.innerHeight - 1);
    const xCandidates = [
      item.rect.left + 8,
      item.rect.left - 8,
      item.rect.left + 18,
    ].filter((x) => x >= 0 && x < window.innerWidth);
    for (const x of xCandidates) {
      const pointTarget = document.elementFromPoint(x, y);
      if (pointTarget && !pointTarget.closest('a')) {
        pointTarget.click();
        return {success: true, method: 'agreement_left_point'};
      }
    }

    item.el.click();
    return {success: true, method: 'agreement_container'};
  }

  const bodyText = document.body ? (document.body.innerText || '') : '';
  if (/登录即同意/.test(bodyText) && /用户协议/.test(bodyText) && /隐私政策/.test(bodyText)) {
    return {success: true, method: 'implicit_agreement'};
  }

  return {success: false, error: 'Agreement checkbox not found'};
})()
""",
    )


def _click_get_code(run_js_fn):
    return _run_js_dict(
        run_js_fn,
        """
(() => {
  const visible = (el) => {
    const style = window.getComputedStyle(el);
    return style && style.visibility !== 'hidden' && style.display !== 'none' &&
      (el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  };
  const textOf = (el) => [
    el.placeholder || '',
    el.type || '',
    el.name || '',
    el.id || '',
    el.autocomplete || '',
    el.inputMode || ''
  ].join(' ').toLowerCase();
  const codeInput = Array.from(document.querySelectorAll('input')).find((el) => {
    return visible(el) && /(验证码|code)/i.test(textOf(el));
  });
  const nodes = Array.from(
    document.querySelectorAll('button,[role="button"],a,div,span')
  ).filter(visible).map((el) => {
    const text = (el.innerText || el.textContent || '').trim().replace(/\\s+/g, '');
    return {el, text};
  }).filter((item) => {
    return /^(获取验证码|发送验证码)$/.test(item.text) && !/收不到/.test(item.text);
  });

  if (!nodes.length) {
    return {success: false, error: 'Get-code button not found'};
  }

  nodes.sort((a, b) => {
    const score = (item) => {
      let value = item.text === '发送验证码' || item.text === '获取验证码' ? 0 : 20;
      if (codeInput) {
        const inputRect = codeInput.getBoundingClientRect();
        const rect = item.el.getBoundingClientRect();
        const inputCenterY = inputRect.top + inputRect.height / 2;
        const centerY = rect.top + rect.height / 2;
        const sameRow = rect.bottom >= inputRect.top - 8 && rect.top <= inputRect.bottom + 8;
        const rightOfCodeInput = rect.left >= inputRect.left + inputRect.width * 0.45;
        const horizontalDistance = Math.max(0, rect.left - inputRect.right);
        value += Math.abs(centerY - inputCenterY) / 10;
        if (sameRow) {
          value -= 30;
        }
        if (rightOfCodeInput) {
          value -= 20;
        }
        value += Math.min(horizontalDistance / 20, 20);
      }
      return value;
    };
    return score(a) - score(b);
  });

  const target = nodes[0].el;
  if (target.disabled || target.getAttribute('aria-disabled') === 'true') {
    return {success: false, error: 'Get-code button is disabled', text: nodes[0].text};
  }

  target.click();
  return {success: true, text: nodes[0].text};
})()
""",
    )


def run(
    phone_number,
    login_url=DEFAULT_LOGIN_URL,
    wait_seconds=1,
    *,
    goto_fn=None,
    run_js_fn=None,
    wait_fn=None,
    get_url_fn=None,
    get_text_fn=None,
    log_fn=None,
):
    """Prepare Xiaohongshu SMS login and stop before manual code entry."""
    if goto_fn is None:
        goto_fn = _controls.goto if _controls is not None else goto
    if run_js_fn is None:
        run_js_fn = _controls.run_js if _controls is not None else run_js
    if wait_fn is None:
        wait_fn = _controls.wait if _controls is not None else wait
    if get_url_fn is None:
        get_url_fn = _controls.get_page_url if _controls is not None else get_url
    if get_text_fn is None:
        get_text_fn = _controls.get_page_text if _controls is not None else get_text

    log_fn = _resolve_log(log_fn)
    steps = []

    try:
        phone = _normalize_phone_number(phone_number)

        nav_result = goto_fn(login_url)
        steps.append({"step": "navigate", "result": nav_result})
        if wait_seconds:
            steps.append({"step": "wait_after_navigation", "result": wait_fn(wait_seconds)})

        blocked = _detect_blocked(get_url_fn, get_text_fn)
        if blocked:
            blocked["steps"] = steps
            log_fn("Xiaohongshu login blocked by security restriction")
            return blocked

        open_result = _open_login_panel(run_js_fn)
        steps.append({"step": "open_login_panel", "result": open_result})
        if wait_seconds:
            steps.append({"step": "wait_after_open_login", "result": wait_fn(wait_seconds)})

        fill_result = _fill_phone(run_js_fn, phone)
        steps.append({"step": "fill_phone", "result": fill_result})
        if not fill_result.get("success"):
            return {
                "success": False,
                "error": "Failed to fill Xiaohongshu phone number",
                "steps": steps,
            }

        agreement_result = _accept_agreement(run_js_fn)
        steps.append({"step": "accept_agreement", "result": agreement_result})
        if not agreement_result.get("success"):
            return {
                "success": False,
                "error": "Failed to accept Xiaohongshu agreement",
                "steps": steps,
            }

        get_code_result = _click_get_code(run_js_fn)
        steps.append({"step": "click_get_code", "result": get_code_result})
        if not get_code_result.get("success"):
            return {
                "success": False,
                "error": "Failed to request Xiaohongshu verification code",
                "steps": steps,
            }

        if wait_seconds:
            steps.append({"step": "wait_after_get_code", "result": wait_fn(wait_seconds)})

        blocked = _detect_blocked(get_url_fn, get_text_fn)
        if blocked:
            blocked["steps"] = steps
            log_fn("Xiaohongshu requires extra verification after requesting code")
            return blocked

        log_fn("Xiaohongshu verification code requested; manual code entry required")
        return {
            "success": True,
            "requires_manual_code": True,
            "phone_number": phone,
            "steps": steps,
            "message": "Please enter the SMS verification code manually in the browser.",
        }

    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        log_fn(f"Xiaohongshu login preparation failed: {error}")
        return {"success": False, "error": error, "steps": steps}
