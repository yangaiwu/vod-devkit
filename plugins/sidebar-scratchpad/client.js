window.__ModuleLoader__.load({
  id: '@local/sidebar-scratchpad',
  factory(require) {
    const React = require('react');
    const h = React.createElement;

    /** Panel id shared by the sidebar entry and the main-panel cell. */
    const PANEL_ID = 'scratchpad';
    /** Client locale namespace for the sidebar label and panel copy. */
    const NS = 'scratchpad';
    /** Browser-local storage key; namespaced so it cannot collide with host state. */
    const STORAGE_KEY = 'dsh.sidebar-scratchpad.note.v1';

    const en = {
      'panel.label': 'Scratchpad',
      'panel.title': 'Scratchpad',
      'panel.subtitle': 'A quick note that autosaves in this browser.',
      'editor.label': 'Scratchpad note',
      'editor.placeholder': 'Start typing…',
      'status.saved': 'Saved',
      'status.saving': 'Saving…',
      'status.unavailable': 'Not saved',
      'status.count': '{count} characters',
      'actions.clear': 'Clear',
      'notice.unavailable': 'This browser blocked local storage, so the note will not survive a reload.',
      'footer.hint': 'Stored only in this browser. It never leaves your machine.',
    };

    const zh = {
      'panel.label': '便签',
      'panel.title': '便签',
      'panel.subtitle': '随手记一笔，自动保存在当前浏览器。',
      'editor.label': '便签内容',
      'editor.placeholder': '开始输入…',
      'status.saved': '已保存',
      'status.saving': '保存中…',
      'status.unavailable': '未保存',
      'status.count': '{count} 个字符',
      'actions.clear': '清空',
      'notice.unavailable': '当前浏览器禁用了本地存储，刷新后便签内容会丢失。',
      'footer.hint': '仅保存在当前浏览器，不会离开这台机器。',
    };

    /** Read the saved note once, tolerating browsers that block storage. */
    function readNote() {
      try {
        return { text: window.localStorage.getItem(STORAGE_KEY) ?? '', ok: true };
      } catch {
        return { text: '', ok: false };
      }
    }

    /** A document with a folded corner and two text lines. */
    function NoteIcon({ size = 18, active = false }) {
      return h(
        'svg',
        {
          viewBox: '0 0 24 24',
          width: size,
          height: size,
          fill: 'none',
          stroke: 'currentColor',
          strokeWidth: active ? 1.8 : 1.5,
          strokeLinecap: 'round',
          strokeLinejoin: 'round',
          'aria-hidden': 'true',
          style: { display: 'block' },
        },
        h('path', {
          d: 'M6.5 3.5h7.2l4.3 4.3v12.2a1.5 1.5 0 0 1-1.5 1.5H6.5A1.5 1.5 0 0 1 5 20V5a1.5 1.5 0 0 1 1.5-1.5Z',
        }),
        h('path', { d: 'M13.7 3.5v4.3h4.3' }),
        h('path', { d: 'M8.6 12.3h6.8M8.6 15.8h4.4' }),
      );
    }

    const CSS = `
      .dsh-scratchpad {
        box-sizing: border-box;
        display: flex;
        flex-direction: column;
        height: 100%;
        min-height: 0;
        overflow-y: auto;
        background: var(--dsw-alias-bg-base);
        color: var(--dsw-alias-label-primary);
      }
      .dsh-scratchpad__inner {
        box-sizing: border-box;
        display: flex;
        flex: 1 1 auto;
        flex-direction: column;
        gap: 20px;
        width: 100%;
        max-width: 760px;
        margin: 0 auto;
        padding: 40px 32px 32px;
      }
      .dsh-scratchpad__header {
        display: flex;
        align-items: flex-start;
        gap: 12px;
      }
      .dsh-scratchpad__mark {
        display: flex;
        align-items: center;
        justify-content: center;
        flex: none;
        width: 36px;
        height: 36px;
        border: 1px solid var(--dsw-alias-border-l1);
        border-radius: 10px;
        background: var(--dsw-alias-bg-layer-1);
        color: var(--dsw-alias-brand-primary);
      }
      .dsh-scratchpad__heading {
        display: flex;
        flex-direction: column;
        gap: 4px;
        min-width: 0;
      }
      .dsh-scratchpad__title {
        margin: 0;
        font-size: 22px;
        font-weight: 600;
        line-height: 1.3;
        color: var(--dsw-alias-label-primary);
      }
      .dsh-scratchpad__subtitle {
        margin: 0;
        font-size: 13.5px;
        line-height: 1.6;
        color: var(--dsw-alias-label-secondary);
      }
      .dsh-scratchpad__notice {
        padding: 10px 14px;
        border: 1px solid var(--dsw-alias-state-warn-primary);
        border-radius: 10px;
        color: var(--dsw-alias-label-primary);
        font-size: 12.5px;
        line-height: 1.6;
      }
      .dsh-scratchpad__card {
        display: flex;
        flex: 1 1 auto;
        flex-direction: column;
        min-height: 260px;
        overflow: hidden;
        border: 1px solid var(--dsw-alias-border-l1);
        border-radius: 14px;
        background: var(--dsw-alias-bg-layer-1);
      }
      .dsh-scratchpad__textarea {
        box-sizing: border-box;
        flex: 1 1 auto;
        width: 100%;
        min-height: 220px;
        padding: 18px;
        border: 0;
        outline: none;
        background: transparent;
        color: var(--dsw-alias-label-primary);
        font: inherit;
        font-size: 14px;
        line-height: 1.75;
        resize: none;
      }
      .dsh-scratchpad__textarea::placeholder {
        color: var(--dsw-alias-label-secondary);
        opacity: 0.75;
      }
      .dsh-scratchpad__textarea:focus-visible {
        box-shadow: inset 0 0 0 2px var(--dsw-alias-brand-primary);
      }
      .dsh-scratchpad__footer {
        display: flex;
        align-items: center;
        justify-content: space-between;
        flex-wrap: wrap;
        gap: 8px 16px;
        padding: 9px 10px 9px 18px;
        border-top: 1px solid var(--dsw-alias-border-l1);
        color: var(--dsw-alias-label-secondary);
        font-size: 12px;
      }
      .dsh-scratchpad__meta {
        display: flex;
        align-items: center;
        gap: 8px;
        min-width: 0;
      }
      .dsh-scratchpad__dot {
        width: 6px;
        height: 6px;
        border-radius: 50%;
        background: var(--dsw-alias-state-success-primary);
        flex: none;
      }
      .dsh-scratchpad__dot[data-status="unavailable"] {
        background: var(--dsw-alias-state-warn-primary);
      }
      .dsh-scratchpad__clear {
        padding: 6px 12px;
        border: 1px solid var(--dsw-alias-border-l1);
        border-radius: 8px;
        background: transparent;
        color: var(--dsw-alias-label-primary);
        font: inherit;
        font-size: 12px;
        cursor: pointer;
      }
      .dsh-scratchpad__clear:hover:not(:disabled) {
        background: var(--dsw-alias-bg-layer-2);
      }
      .dsh-scratchpad__clear:focus-visible {
        outline: 2px solid var(--dsw-alias-brand-primary);
        outline-offset: 1px;
      }
      .dsh-scratchpad__clear:disabled {
        opacity: 0.45;
        cursor: default;
      }
      .dsh-scratchpad__hint {
        margin: 0;
        font-size: 12px;
        line-height: 1.6;
        color: var(--dsw-alias-label-secondary);
      }
      @media (max-width: 640px) {
        .dsh-scratchpad__inner {
          padding: 24px 18px;
        }
      }
    `;

    /** Central panel: a browser-local note with debounced autosave. */
    function ScratchpadPanel({ t }) {
      const [initial] = React.useState(readNote);
      const [value, setValue] = React.useState(initial.text);
      const [status, setStatus] = React.useState(initial.ok ? 'saved' : 'unavailable');
      const firstRender = React.useRef(true);

      React.useEffect(() => {
        if (firstRender.current) {
          firstRender.current = false;
          return undefined;
        }
        setStatus('saving');
        const timer = window.setTimeout(() => {
          try {
            window.localStorage.setItem(STORAGE_KEY, value);
            setStatus('saved');
          } catch {
            setStatus('unavailable');
          }
        }, 250);
        return () => window.clearTimeout(timer);
      }, [value]);

      const label =
        status === 'unavailable'
          ? t('status.unavailable')
          : status === 'saving'
            ? t('status.saving')
            : t('status.saved');

      return h(
        'section',
        { className: 'dsh-scratchpad', 'aria-label': t('panel.title'), 'data-testid': 'sidebar-scratchpad' },
        h('style', null, CSS),
        h(
          'div',
          { className: 'dsh-scratchpad__inner' },
          h(
            'header',
            { className: 'dsh-scratchpad__header' },
            h('span', { className: 'dsh-scratchpad__mark' }, h(NoteIcon, { size: 20 })),
            h(
              'div',
              { className: 'dsh-scratchpad__heading' },
              h('h1', { className: 'dsh-scratchpad__title' }, t('panel.title')),
              h('p', { className: 'dsh-scratchpad__subtitle' }, t('panel.subtitle')),
            ),
          ),
          status === 'unavailable' ? h('div', { className: 'dsh-scratchpad__notice' }, t('notice.unavailable')) : null,
          h(
            'div',
            { className: 'dsh-scratchpad__card' },
            h('textarea', {
              className: 'dsh-scratchpad__textarea',
              value,
              placeholder: t('editor.placeholder'),
              'aria-label': t('editor.label'),
              spellCheck: false,
              onChange: (event) => setValue(event.target.value),
            }),
            h(
              'footer',
              { className: 'dsh-scratchpad__footer' },
              h(
                'span',
                { className: 'dsh-scratchpad__meta', role: 'status', 'aria-live': 'polite' },
                h('span', { className: 'dsh-scratchpad__dot', 'data-status': status }),
                h('span', null, label),
                h('span', { 'aria-hidden': 'true' }, '·'),
                h('span', null, t('status.count', { count: value.length })),
              ),
              h(
                'button',
                {
                  type: 'button',
                  className: 'dsh-scratchpad__clear',
                  disabled: value.length === 0,
                  onClick: () => setValue(''),
                },
                t('actions.clear'),
              ),
            ),
          ),
          h('p', { className: 'dsh-scratchpad__hint' }, t('footer.hint')),
        ),
      );
    }

    /** Sidebar glyph; the shell draws the button, tooltip, and selected state. */
    function ScratchpadIcon({ size, active }) {
      return h(NoteIcon, { size, active });
    }

    return {
      inject: ['slots', 'locale'],
      apply(ctx) {
        ctx.effect(
          () => ctx.locale.register(NS, { zh, en }),
          'sidebar-scratchpad: dictionaries',
        );
        const t = ctx.locale.bind(NS);
        ctx.slots.inject('main', () =>
          ctx.slots.register({ name: 'main', key: PANEL_ID, locale: NS }, ScratchpadPanel),
        );
        ctx.slots.inject('sidebar.panellist', () =>
          ctx.slots.register(
            {
              name: 'sidebar.panellist',
              id: PANEL_ID,
              order: 20,
              locale: NS,
              label: () => t('panel.label'),
            },
            ScratchpadIcon,
          ),
        );
      },
    };
  },
});
