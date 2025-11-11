(function(){
  const FIELD_TYPES = [
    { value: 'text', label: 'Text' },
    { value: 'textarea', label: 'Long text' },
    { value: 'number', label: 'Integer number' },
    { value: 'decimal', label: 'Decimal number' },
    { value: 'boolean', label: 'Checkbox' },
    { value: 'select', label: 'Dropdown (single choice)' },
    { value: 'radio', label: 'Radio buttons' },
    { value: 'multiselect', label: 'Multi select (checkboxes)' },
    { value: 'date', label: 'Date' },
    { value: 'time', label: 'Time' },
    { value: 'datetime', label: 'Date & time' },
    { value: 'email', label: 'Email' },
    { value: 'phone', label: 'Phone' },
  ];

  const CHOICE_TYPES = new Set(['select', 'radio', 'multiselect', 'radiolist', 'multichoice']);

  const SAMPLE_SCHEMA = {
    meta: { version: 1 },
    sections: [
      {
        id: 'sample-section-general',
        title: 'Client overview',
        fields: [
          {
            id: 'sample-field-full-name',
            key: 'full_name',
            label: 'Full name',
            type: 'text',
            placeholder: 'Jane Doe',
          },
          {
            id: 'sample-field-medications',
            key: 'medications',
            label: 'Current medications',
            type: 'textarea',
          },
          {
            id: 'sample-field-consent',
            key: 'consent',
            label: 'Consent granted',
            type: 'checkbox',
          },
        ],
      },
      {
        id: 'sample-section-skin',
        title: 'Skin profile',
        fields: [
          {
            id: 'sample-field-skin-type',
            key: 'skin_type',
            label: 'Skin type',
            type: 'radio',
            choices: [
              { value: 'normal', label: 'Normal' },
              { value: 'dry', label: 'Dry' },
              { value: 'oily', label: 'Oily' },
              { value: 'combination', label: 'Combination' },
            ],
          },
          {
            id: 'sample-field-allergies',
            key: 'allergies',
            label: 'Known allergies',
            type: 'multiselect',
            choices: [
              { value: 'pollen', label: 'Pollen' },
              { value: 'nuts', label: 'Nuts' },
              { value: 'fragrance', label: 'Fragrance' },
              { value: 'lidocaine', label: 'Lidocaine' },
            ],
          },
        ],
      },
    ],
  };

  function uuid(){
    if (window.crypto && crypto.randomUUID){
      return crypto.randomUUID();
    }
    return 'id-' + Math.random().toString(36).slice(2, 10);
  }

  function slugify(value){
    return (value || '')
      .toString()
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/^_+|_+$/g, '')
      .slice(0, 48);
  }

  function clone(obj){
    return JSON.parse(JSON.stringify(obj));
  }

  function parseJSON(str){
    try {
      return str ? JSON.parse(str) : null;
    } catch(_err){
      return null;
    }
  }

  function normalizeField(field){
    const base = field && typeof field === 'object' ? field : {};
    const normalized = {
      id: base.id || uuid(),
      label: base.label || '',
      key: base.key || '',
      type: (base.type || 'text').toLowerCase(),
      required: Boolean(base.required),
      placeholder: base.placeholder || '',
      help_text: base.help_text || '',
      default: base.default !== undefined ? base.default : '',
      display: base.display && typeof base.display === 'object' ? {...base.display} : {},
      settings: base.settings && typeof base.settings === 'object' ? {...base.settings} : {},
      choices: [],
      __autoKey: base.__autoKey || null,
    };
    if (Array.isArray(base.choices)){
      normalized.choices = base.choices.map(choice => ({
        id: choice && choice.id ? choice.id : uuid(),
        value: choice && choice.value !== undefined ? choice.value : '',
        label: choice && choice.label !== undefined ? choice.label : '',
        default: Boolean(choice && choice.default),
      }));
    }
    return normalized;
  }

  function normalizeSection(section){
    const base = section && typeof section === 'object' ? section : {};
    return {
      id: base.id || uuid(),
      title: base.title || '',
      description: base.description || '',
      fields: Array.isArray(base.fields) ? base.fields.map(normalizeField) : [],
    };
  }

  function ensureSchema(raw){
    const schema = { sections: [], meta: { version: 1 } };
    if (raw && typeof raw === 'object'){
      if (Array.isArray(raw.sections)){
        schema.sections = raw.sections.map(normalizeSection);
      }
      if (raw.meta && typeof raw.meta === 'object'){
        schema.meta = {...raw.meta};
        if (!schema.meta.version) schema.meta.version = 1;
      }
    }
    if (!schema.meta) schema.meta = { version: 1 };
    if (!schema.meta.version) schema.meta.version = 1;
    return schema;
  }

  function locateActionsHost(){
    const selectors = [
      '#jazzy-actions .card-body',
      '#jazzy-actions',
      '.submit-row',
      '.form-actions',
    ];
    for (const selector of selectors){
      const el = document.querySelector(selector);
      if (el) return { element: el, selector };
    }
    return null;
  }

  function ensureGuidePanel({ element, selector }){
    if (!element) return null;
    if (selector === '#jazzy-actions'){
      const cardBody = element.querySelector('.card-body');
      if (cardBody){
        element = cardBody;
      }
    }
    if (selector === '.submit-row'){
      let next = element.nextElementSibling;
      while (next && !next.classList.contains('ibuilder-guide-panel')){
        next = next.nextElementSibling;
      }
      if (next && next.classList.contains('ibuilder-guide-panel')){
        return next;
      }
      const panel = document.createElement('div');
      panel.className = 'ibuilder-guide-panel';
      element.insertAdjacentElement('afterend', panel);
      return panel;
    }

    let panel = element.querySelector('.ibuilder-guide-panel');
    if (!panel){
      panel = document.createElement('div');
      panel.className = 'ibuilder-guide-panel';
      element.appendChild(panel);
    }
    return panel;
  }

  function relocateGuideToActionsPanel(root, attempt = 0){
    if (!root || root.dataset.guideRelocated === '1') return;
    const guide = root.querySelector('.ibuilder__guide');
    if (!guide) return;

    const hostInfo = locateActionsHost();
    if (!hostInfo){
      if (attempt < 10){
        const delay = Math.min(600, 150 + attempt * 50);
        setTimeout(() => relocateGuideToActionsPanel(root, attempt + 1), delay);
      }
      return;
    }
    const panel = ensureGuidePanel(hostInfo);
    if (!panel) return;
    panel.appendChild(guide);
    root.dataset.guideRelocated = '1';
  }

  function createDefaultField(){
    const key = slugify('field_' + Math.random().toString(36).slice(2,6));
    return {
      id: uuid(),
      label: 'Question',
      key: key,
      type: 'text',
      required: false,
      placeholder: '',
      help_text: '',
      default: '',
      display: { width: 'full' },
      settings: {},
      choices: [],
      __autoKey: key,
    };
  }

  function createDefaultSection(){
    return {
      id: uuid(),
      title: 'Section',
      description: '',
      fields: [],
    };
  }

  function cleanState(state){
    const cleaned = { meta: {...state.meta}, sections: [] };
    cleaned.sections = state.sections.map(section => ({
      id: section.id,
      title: section.title,
      description: section.description,
      fields: section.fields.map(field => {
        const f = clone(field);
        delete f.__autoKey;
        if (f.display && !Object.keys(f.display).length) delete f.display;
        if (f.settings && !Object.keys(f.settings).length) delete f.settings;
        if (f.choices && Array.isArray(f.choices)){
          f.choices = f.choices.map(choice => {
            const c = {...choice};
            delete c.id;
            return c;
          });
          if (!f.choices.length) delete f.choices;
        }
        return f;
      }),
    }));
    return cleaned;
  }

  function createButton(label, className){
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = className;
    btn.textContent = label;
    return btn;
  }

  function createInputGroup(labelText, value, onChange, options = {}){
    const wrap = document.createElement('div');
    wrap.className = 'ibuilder-field__row-item';
    const label = document.createElement('label');
    label.textContent = labelText;
    const input = options.textarea ? document.createElement('textarea') : document.createElement('input');
    if (!options.textarea){
      input.type = options.type || 'text';
    }
    if (options.placeholder) input.placeholder = options.placeholder;
    input.value = value != null ? value : '';
    input.addEventListener('input', () => onChange(options.textarea ? input.value : input.value));
    wrap.appendChild(label);
    wrap.appendChild(input);
    return { wrap, input };
  }

  function createSelectGroup(labelText, value, optionsList, onChange){
    const wrap = document.createElement('div');
    wrap.className = 'ibuilder-field__row-item';
    const label = document.createElement('label');
    label.textContent = labelText;
    const select = document.createElement('select');
    optionsList.forEach(opt => {
      const option = new Option(opt.label, opt.value);
      select.appendChild(option);
    });
    select.value = value;
    select.addEventListener('change', () => onChange(select.value));
    wrap.appendChild(label);
    wrap.appendChild(select);
    return { wrap, select };
  }

  class IntakeBuilder {
    constructor(root){
      this.root = root;
      this.input = root.querySelector('input[type="hidden"]');
      this.sectionsMount = root.querySelector('[data-builder-sections]');
      this.jsonPanel = root.querySelector('[data-json-panel]');
      this.jsonTextarea = this.jsonPanel ? this.jsonPanel.querySelector('[data-json-textarea]') : null;
      const initialPayload = (() => {
        const fromDataset = root.dataset.initial;
        if (fromDataset && fromDataset.trim().length){
          const parsed = parseJSON(fromDataset);
          if (parsed) return parsed;
        }
        if (this.input && this.input.value){
          const parsed = parseJSON(this.input.value);
          if (parsed) return parsed;
        }
        return null;
      })();
      const initial = initialPayload || {};
      this.state = ensureSchema(initial);
      this.bindToolbar();
      this.render();
      relocateGuideToActionsPanel(this.root);
    }

    bindToolbar(){
      const addSectionBtn = this.root.querySelector('[data-action="add-section"]');
      const sampleBtn = this.root.querySelector('[data-action="load-sample"]');
      const toggleJsonBtn = this.root.querySelector('[data-action="toggle-json"]');

      if (addSectionBtn){
        addSectionBtn.addEventListener('click', () => {
          this.state.sections.push(createDefaultSection());
          this.render();
        });
      }
      if (sampleBtn){
        sampleBtn.addEventListener('click', () => {
          this.state = ensureSchema(clone(SAMPLE_SCHEMA));
          this.render();
        });
      }
      if (toggleJsonBtn){
        toggleJsonBtn.addEventListener('click', () => this.toggleJsonPanel());
      }
      if (this.jsonPanel){
        const applyBtn = this.jsonPanel.querySelector('[data-action="apply-json"]');
        const resetBtn = this.jsonPanel.querySelector('[data-action="reset-json"]');
        if (applyBtn){
          applyBtn.addEventListener('click', () => this.applyJsonFromTextarea());
        }
        if (resetBtn){
          resetBtn.addEventListener('click', () => {
            this.populateJsonTextarea();
          });
        }
      }
    }

    generateUniqueKey(preferredKey, fieldId){
      const preferred = slugify(preferredKey || '');
      const randomSeed = slugify(`field_${Math.random().toString(36).slice(2,6)}`);
      let candidate = preferred || randomSeed || `field_${Math.random().toString(36).slice(2,6)}`;
      const root = candidate;
      const hasDuplicate = key => this.state.sections.some(section =>
        section.fields.some(f => f.id !== fieldId && f.key === key)
      );
      let suffix = 1;
      while (hasDuplicate(candidate)){
        candidate = `${root}_${suffix++}`;
      }
      return candidate;
    }

    setInputValue(){
      if (!this.input) return;
      const cleaned = cleanState(this.state);
      this.input.value = JSON.stringify(cleaned);
    }

    toggleJsonPanel(){
      if (!this.jsonPanel) return;
      const isHidden = this.jsonPanel.hasAttribute('hidden');
      if (isHidden){
        this.populateJsonTextarea();
        this.jsonPanel.removeAttribute('hidden');
      } else {
        this.jsonPanel.setAttribute('hidden', 'hidden');
      }
    }

    populateJsonTextarea(){
      if (!this.jsonTextarea) return;
      this.jsonTextarea.value = JSON.stringify(cleanState(this.state), null, 2);
    }

    applyJsonFromTextarea(){
      if (!this.jsonTextarea) return;
      try {
        const parsed = JSON.parse(this.jsonTextarea.value);
        this.state = ensureSchema(parsed);
        this.render();
      } catch (err){
        alert('Invalid JSON: ' + err.message);
      }
    }

    render(){
      if (!this.sectionsMount) return;
      this.sectionsMount.innerHTML = '';
      this.state.sections.forEach((section, index) => {
        if (!section.fields) section.fields = [];
        this.sectionsMount.appendChild(this.renderSection(section, index));
      });
      this.setInputValue();
      if (this.jsonPanel && !this.jsonPanel.hasAttribute('hidden')){
        this.populateJsonTextarea();
      }
    }

    renderSection(section, index){
      const wrap = document.createElement('div');
      wrap.className = 'ibuilder-section';

      const header = document.createElement('div');
      header.className = 'ibuilder-section__header';

      const titleWrap = document.createElement('div');
      titleWrap.className = 'ibuilder-section__title';
      const titleInput = document.createElement('input');
      titleInput.type = 'text';
      titleInput.value = section.title || '';
      titleInput.placeholder = 'Section title';
      titleInput.addEventListener('input', () => {
        section.title = titleInput.value;
        this.setInputValue();
      });
      titleWrap.appendChild(titleInput);

      const controls = document.createElement('div');
      controls.className = 'ibuilder-section__controls';

      const upBtn = createButton('Up', 'ibuilder__btn ibuilder__btn--ghost');
      upBtn.disabled = index === 0;
      upBtn.addEventListener('click', () => {
        if (index === 0) return;
        const tmp = this.state.sections[index - 1];
        this.state.sections[index - 1] = this.state.sections[index];
        this.state.sections[index] = tmp;
        this.render();
      });

      const downBtn = createButton('Down', 'ibuilder__btn ibuilder__btn--ghost');
      downBtn.disabled = index === this.state.sections.length - 1;
      downBtn.addEventListener('click', () => {
        if (index === this.state.sections.length - 1) return;
        const tmp = this.state.sections[index + 1];
        this.state.sections[index + 1] = this.state.sections[index];
        this.state.sections[index] = tmp;
        this.render();
      });

      const removeBtn = createButton('Delete', 'ibuilder__btn ibuilder__btn--danger');
      removeBtn.addEventListener('click', () => {
        if (confirm('Remove this section?')){
          this.state.sections.splice(index, 1);
          this.render();
        }
      });

      controls.appendChild(upBtn);
      controls.appendChild(downBtn);
      controls.appendChild(removeBtn);

      header.appendChild(titleWrap);
      header.appendChild(controls);
      wrap.appendChild(header);

      const fieldsWrap = document.createElement('div');
      fieldsWrap.className = 'ibuilder-section__fields';

      section.fields.forEach((field, fieldIndex) => {
        fieldsWrap.appendChild(this.renderField(section, index, field, fieldIndex));
      });

      const addFieldBtn = createButton('Add field', 'ibuilder__btn');
      addFieldBtn.addEventListener('click', () => {
        section.fields.push(createDefaultField());
        this.render();
      });

      fieldsWrap.appendChild(addFieldBtn);
      wrap.appendChild(fieldsWrap);
      return wrap;
    }

    renderField(section, sectionIndex, field, fieldIndex){
      const wrap = document.createElement('div');
      wrap.className = 'ibuilder-field';

      const rowPrimary = document.createElement('div');
      rowPrimary.className = 'ibuilder-field__row';

      const syncAutoKey = value => {
        const auto = slugify(value);
        if (!auto) return;
        if (!field.key || field.key === field.__autoKey){
          const nextKey = this.generateUniqueKey(auto, field.id);
          field.key = nextKey;
          field.__autoKey = nextKey;
        }
      };

      const labelGroup = createInputGroup('Label', field.label, value => {
        field.label = value;
        syncAutoKey(value);
        this.setInputValue();
      });
      labelGroup.wrap.classList.add('ibuilder-field__row-item');

      const typeGroup = createSelectGroup('Type', field.type, FIELD_TYPES, value => {
        field.type = value;
        if (!CHOICE_TYPES.has(value)){
          field.choices = [];
        } else if (!Array.isArray(field.choices) || !field.choices.length){
          field.choices = [
            { id: uuid(), label: 'Option 1', value: 'option_1', default: false },
            { id: uuid(), label: 'Option 2', value: 'option_2', default: false },
          ];
        }
        this.render();
      });
      typeGroup.wrap.classList.add('ibuilder-field__row-item');

      rowPrimary.appendChild(labelGroup.wrap);
      rowPrimary.appendChild(typeGroup.wrap);
      wrap.appendChild(rowPrimary);

      const rowSecondary = document.createElement('div');
      rowSecondary.className = 'ibuilder-field__row';
      const placeholderGroup = createInputGroup('Placeholder', field.placeholder, value => {
        field.placeholder = value;
        this.setInputValue();
      });
      placeholderGroup.wrap.classList.add('ibuilder-field__row-item');

      rowSecondary.appendChild(placeholderGroup.wrap);
      wrap.appendChild(rowSecondary);

      if (CHOICE_TYPES.has(field.type)){
        const optionsWrap = document.createElement('div');
        optionsWrap.className = 'ibuilder-field__options';
        const heading = document.createElement('h5');
        heading.textContent = 'Options';
        optionsWrap.appendChild(heading);

        const list = document.createElement('div');
        field.choices = Array.isArray(field.choices) ? field.choices : [];
        field.choices.forEach((choice, choiceIndex) => {
          const row = document.createElement('div');
          row.className = 'ibuilder-option';
          const valueInput = document.createElement('input');
          valueInput.type = 'text';
          valueInput.placeholder = 'Value';
          valueInput.value = choice.value != null ? choice.value : '';
          valueInput.addEventListener('input', () => {
            choice.value = valueInput.value;
            this.setInputValue();
          });
          const labelInput = document.createElement('input');
          labelInput.type = 'text';
          labelInput.placeholder = 'Label';
          labelInput.value = choice.label != null ? choice.label : '';
          labelInput.addEventListener('input', () => {
            choice.label = labelInput.value;
            this.setInputValue();
          });
          const defaultToggle = document.createElement('input');
          defaultToggle.type = field.type === 'multiselect' ? 'checkbox' : 'radio';
          defaultToggle.name = `choice-default-${field.id}`;
          defaultToggle.checked = Boolean(choice.default);
          defaultToggle.addEventListener('change', () => {
            if (field.type === 'multiselect'){
              choice.default = defaultToggle.checked;
            } else {
              field.choices.forEach((opt, idx) => {
                opt.default = idx === choiceIndex;
              });
            }
            this.setInputValue();
          });
          const removeBtn = document.createElement('button');
          removeBtn.type = 'button';
          removeBtn.textContent = '×';
          removeBtn.title = 'Remove option';
          removeBtn.addEventListener('click', () => {
            field.choices.splice(choiceIndex, 1);
            this.render();
          });
          row.appendChild(valueInput);
          row.appendChild(labelInput);
          row.appendChild(defaultToggle);
          row.appendChild(removeBtn);
          list.appendChild(row);
        });

        const addOptionBtn = createButton('Add option', 'ibuilder__btn ibuilder__btn--ghost');
        addOptionBtn.addEventListener('click', () => {
          field.choices.push({ id: uuid(), value: '', label: '', default: false });
          this.render();
        });

        optionsWrap.appendChild(list);
        optionsWrap.appendChild(addOptionBtn);
        wrap.appendChild(optionsWrap);
      }

      if (field.type === 'number' || field.type === 'integer' || field.type === 'decimal' || field.type === 'float'){
        const numericWrap = document.createElement('div');
        numericWrap.className = 'ibuilder-field__row';
        const minGroup = createInputGroup('Min', field.settings.min_value || '', value => {
          field.settings = field.settings || {};
          field.settings.min_value = value;
          this.setInputValue();
        });
        const maxGroup = createInputGroup('Max', field.settings.max_value || '', value => {
          field.settings = field.settings || {};
          field.settings.max_value = value;
          this.setInputValue();
        });
        numericWrap.appendChild(minGroup.wrap);
        numericWrap.appendChild(maxGroup.wrap);
        if (field.type === 'decimal' || field.type === 'float'){
          const precisionGroup = createInputGroup('Decimal places', field.settings.decimal_places != null ? field.settings.decimal_places : 2, value => {
            field.settings = field.settings || {};
            field.settings.decimal_places = value;
            this.setInputValue();
          });
          numericWrap.appendChild(precisionGroup.wrap);
        }
        wrap.appendChild(numericWrap);
      }

      const actionBar = document.createElement('div');
      actionBar.className = 'ibuilder-field__actionbar';

      const duplicateBtn = createButton('Duplicate', 'ibuilder__btn ibuilder__btn--ghost');
      duplicateBtn.addEventListener('click', () => {
        const copy = clone(field);
        copy.id = uuid();
        const baseKey = copy.key ? `${copy.key}_copy` : slugify(copy.label || '') || '';
        copy.key = this.generateUniqueKey(baseKey, copy.id);
        copy.__autoKey = copy.key;
        section.fields.splice(fieldIndex + 1, 0, normalizeField(copy));
        this.render();
      });

      const upBtn = createButton('Up', 'ibuilder__btn ibuilder__btn--ghost');
      upBtn.disabled = fieldIndex === 0;
      upBtn.addEventListener('click', () => {
        if (fieldIndex === 0) return;
        const tmp = section.fields[fieldIndex - 1];
        section.fields[fieldIndex - 1] = section.fields[fieldIndex];
        section.fields[fieldIndex] = tmp;
        this.render();
      });

      const downBtn = createButton('Down', 'ibuilder__btn ibuilder__btn--ghost');
      downBtn.disabled = fieldIndex === section.fields.length - 1;
      downBtn.addEventListener('click', () => {
        if (fieldIndex === section.fields.length - 1) return;
        const tmp = section.fields[fieldIndex + 1];
        section.fields[fieldIndex + 1] = section.fields[fieldIndex];
        section.fields[fieldIndex] = tmp;
        this.render();
      });

      const removeBtn = createButton('Remove', 'ibuilder__btn ibuilder__btn--danger');
      removeBtn.addEventListener('click', () => {
        if (confirm('Remove this field?')){
          section.fields.splice(fieldIndex, 1);
          this.render();
        }
      });

      actionBar.appendChild(duplicateBtn);
      actionBar.appendChild(upBtn);
      actionBar.appendChild(downBtn);
      actionBar.appendChild(removeBtn);
      wrap.appendChild(actionBar);

      return wrap;
    }
  }

  function mountIntakeBuilders(){
    document.querySelectorAll('[data-intake-builder]').forEach(root => {
      if (!root.__intakeBuilderInstance){
        root.__intakeBuilderInstance = new IntakeBuilder(root);
      }
    });
  }

  if (document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', mountIntakeBuilders);
  } else {
    mountIntakeBuilders();
  }

  document.addEventListener('formset:added', mountIntakeBuilders);
  document.addEventListener('formset:removed', mountIntakeBuilders);
})();
