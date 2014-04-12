// Colors corresponding to mastery levels 0-5
var MASTERY_COLORS = ['', '#CA5353', '#DA8143', '#CBDA2E', '#BCDC3B', '#81D43A'];

// Time this page was loaded
var STARTUP_TIME = new Date();

// Detect onpopstate event on page load (https://github.com/defunkt/jquery-pjax/issues/143#issuecomment-6194330)
var INITIAL_URL = location.href;
var PUSHED_STATE = false;
var isOnLoadPopState = function() { return !PUSHED_STATE && location.href == INITIAL_URL; }

// localStorage keys
STORAGE_KEYS_BASE = 'tutorme.capstone';
STORAGE_KEYS = {
    base: STORAGE_KEYS_BASE,
    mastery: STORAGE_KEYS_BASE + '.mastery',
    notes: STORAGE_KEYS_BASE + '.notes',
    color: STORAGE_KEYS_BASE + '.color',
    hilites: STORAGE_KEYS_BASE + '.highlights',
    testlist: STORAGE_KEYS_BASE + '.testlist',
}
var Storage = function(getCurrentKeyFn) {
    // If provided, Storage.currentKey will return an ID for the current question
    this.currentKey = getCurrentKeyFn;

    // --------------------------------------------------------------------------------------------
    // Read/write directly to localStorage using the keys defined in STORAGE_KEYS 
    // (e.g. mastery, notes, ...). Only strings are stored - everything passes through
    // JSON.stringify() / JSON.parse() on read/write.
    // --------------------------------------------------------------------------------------------
    this.read = function(key, def) { return JSON.parse(localStorage.getItem(STORAGE_KEYS[key]) || def); };
    this.write = function(key, val) { localStorage.setItem(STORAGE_KEYS[key], JSON.stringify(val)); };
    this.clear = function(key) { localStorage.removeItem(STORAGE_KEYS[key]); };
    
    // --------------------------------------------------------------------------------------------
    // Read write an entire object or a particular key. The first parameter, name, should be a key
    // in STORAGE_KEYS (e.g. mastery, notes, ...). If the key parameter is not given, return the 
    // entire object.
    // --------------------------------------------------------------------------------------------
    this.getObject = function(name, key) {
        var obj = this.read(name, '{}');
        return (key !== undefined) ? obj[key] : obj;
    };
    this.saveObject = function(name, key, obj) {
        // key argument is optional. When omitted, arguments are (name, obj)
        if (obj === undefined) {
            obj = key;
            key = undefined;
        }
        if (key) {
            var val = obj;
            obj = this.getObject(name);
            obj[key] = val;
        }
        this.write(name, obj);
    };
    this.clearObject = function(name, key) {
        if (key) { 
            var obj = this.getObject(name);
            delete obj[key];
            this.write(name, obj);
        } else {
            this.clear(name);
        }
    };

    // --------------------------------------------------------------------------------------------
    // Convenience functions for specific data
    // --------------------------------------------------------------------------------------------
    this.getMastery          = function(key)         { return this.getObject('mastery', key); };
    this.getCurrentMastery   = function()            { return this.getMastery(this.currentKey()); };
    this.saveMastery         = function(key, val)    { this.saveObject('mastery', key, val); };
    this.saveCurrentMastery  = function(val)         { this.saveMastery(this.currentKey(), val); };
    this.clearMastery        = function(key)         { this.clearObject('mastery', key); };
    this.clearCurrentMastery = function()            { this.clearMastery(this.currentKey()); };
    this.getNotes            = function(key)         { return this.getObject('notes', key); };
    this.getCurrentNotes     = function()            { return this.getNotes('q,' + this.currentKey()); };
    this.saveNotes           = function(key, obj)    { this.saveObject('notes', key, obj); };
    this.saveCurrentNotes    = function(obj)         { this.saveNotes('q,' + this.currentKey(), obj); };
    this.getColor            = function()            { return localStorage.getItem(STORAGE_KEYS['color']) || ''; };
    this.saveColor           = function(val)         { localStorage.setItem(STORAGE_KEYS['color'], val); };
    this.clearColor          = function(val)         { STORAGE.clear('color') };
    this.getHilites          = function(key)         { return this.getObject('hilites', key); };
    this.getCurrentHilites   = function(prefix)      { return this.getHilites(prefix + ',' + this.currentKey()); };
    this.saveHilites         = function(key, obj)    { this.saveObject('hilites', key, obj); };
    this.saveCurrentHilites  = function(prefix, obj) { this.saveHilites(prefix + ',' + this.currentKey(), obj); };
    this.getTestList         = function(key)         { return this.getObject('testlist', key); };
    this.saveTestList        = function(key, obj)    { this.saveObject('testlist', key, obj); };
}

// Return an object with URL query parameters
function getUrlVars() {
    var vars = [],
        hash;
    var hashes = window.location.href.slice(window.location.href.indexOf('?') + 1).split('&');
    for (var i = 0; i < hashes.length; i++) {
        hash = hashes[i].split('=');
        vars.push(hash[0]);
        vars[hash[0]] = hash[1];
    }
    return vars;
}

// Randomize elements in an array
function shuffleArray(array) {
    for (var i = array.length - 1; i > 0; i--) {
        var j = Math.floor(Math.random() * (i + 1));
        var temp = array[i];
        array[i] = array[j];
        array[j] = temp;
    }
    return array;
}

// The total number of questions provided by data.js
function numQuestions() {
    return data.reduce(function(acc, section) {
        return acc + section.questions.length;
    });
}

// Given an id in the format [q,]section #,question #, return the actual question object
function questionFromId(data, id) {
    id = /q,/.test(id) ? id.substr(2) : id;
    var parts = id.split(','),
        s = parseInt(parts[0]),
        q = parseInt(parts[1]);
    return (isNaN(s) || isNaN(q)) ? null : data[s].questions[q];
}

// Get the correct answer from question.correct or the answer text
function correctAnswerFromQuestion(question) {
    if (question.correct) {
        return question.correct;
    } else {
        var pattern = /([A-Z])\s+is\s+correct|answer\s+is\s+([A-Z])/i;
        var matches = question.answer.match(pattern);
        if (matches) {
            return (matches[1] || matches[2]).charCodeAt(0) - 64;
        }
    }
};

// Format milliseconds into hh:mm:ss string
function formatTime(ms, showSeconds) {
    ms = ms || 0;
    var elapsedMin = ms / 1000 / 60,
        h = Math.floor(elapsedMin / 60),
        mm = Math.floor(elapsedMin) % 60,
        ss = Math.floor(ms / 1000) % 60;

    mm = (mm<10 ? '0' : '') + mm;
    ss = (ss<10 ? '0' : '') + ss;
    return h + ':' + mm + (showSeconds ? ':' + ss : '');
}

// Micro-templating (modified from Resig's code). Uses {{ }} to denote an expression. Only
// expressions are supported (i.e. no code blocks)
var tmpl_cache = {};
function tmpl(str, data) {
    // Figure out if we're getting a template, or if we need to
    // load the template - and be sure to cache the result.
    var fn = !/\W/.test(str) ?
        tmpl_cache[str] = tmpl_cache[str] ||
        tmpl(document.getElementById(str).innerHTML) :

    // Generate a reusable function that will serve as a template
    // generator (and which will be cached).
    new Function("obj",
        // Introduce the data as local variables using with(){}
        "var p=[];" +
        "with(obj){p.push('" +

        // Convert the template into pure JavaScript
        str
        .replace(/[\r\t\n]/g, " ")              // clear marker characters to use below
        .replace(/\{\{/g, "\t")                    // replace start token {{ with \t
        .replace(/\t(.*?)}}/g, "',$1,'") +      // replace "\t expr}}" with ',expr,'

        "');}return p.join('');");              // Result is p.push('template text',expr,'more template text')

    // Provide some basic currying to the user
    return data ? fn(data) : fn;
};