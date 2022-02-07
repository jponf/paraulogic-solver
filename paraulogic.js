
let CHARACTERS_TO_IGNORE = ["·", "-", "'", "’"];

/* global variable to keep words data */
var wordsByCharacter = null;
var wordsAffixes = null

/**
 * Initializes the app by fetching data from the server.
 * @param {function} onloaded 
 */
function initGlobalData(onloaded) {
    if (wordsByCharacter === null) {
        var xobj = new XMLHttpRequest();
        xobj.overrideMimeType("application/json");
        xobj.open('GET', 'data/words_v2.json', true);
        xobj.onreadystatechange = function () {
            if (xobj.readyState == 4 && xobj.status == "200") {
                let jsonData = JSON.parse(xobj.responseText);
                onloaded(jsonData["words"]);
            }
        };
        xobj.send();
    } else {
        onloaded();
    }
}

/**
 * Post process words data to simplify the process of finding
 * words given the characters they contain.
 * @param {[string]} wordsData 
 */
function postProcessWords(wordsData) {    
    wordsByCharacter = {}
    wordsAffixes = {}    

    wordsData.forEach(entry => {
        // Separate full words from affixes
        let affixes = [];
        let words = [];
        entry.forEach(item => {
            if (item.startsWith("-") || item.endsWith("-")) {
                affixes.push(item);
            } else {
                words.push(item);
            }
        });

        words.forEach(word => {
            let plainWord = stripDiacritics(word);
            wordsAffixes[plainWord] = affixes;
            for (let i = 0; i < plainWord.length; ++i) {
                let ch = plainWord[i];

                if (!isAnIgnoredCharacter(ch)) {
                    if (!(ch in wordsByCharacter)) {
                        wordsByCharacter[ch] = [plainWord];
                    } else {
                        wordsByCharacter[ch].push(plainWord);
                    }
                }
            }
        });
    });

    for (const key in wordsByCharacter) {
        wordsByCharacter[key] = [... new Set(wordsByCharacter[key])];
        wordsByCharacter[key].sort();
    }
}

/**
 * Removes diacritic marks from the input string.
 * @param {string} text 
 * @returns The string without any diacritic mark.
 */
function stripDiacritics(text) {
    // strip all diacritics except:
    //  - [u+0327] Combining Cedilla (for example: ç)
    return text.normalize("NFD")
               .replace(/[\u0300-\u0326]/g, "")
               .replace(/[\u0328-\u036f]/g, "");
}

function isAnIgnoredCharacter(char) {
    return /\s/.test(char) || CHARACTERS_TO_IGNORE.includes(char);
}

function isWordValid(word, validCharacters) {
    for (let i = 0; i < word.length; ++i) {
        if (
            !isAnIgnoredCharacter(word[i])
            && !validCharacters.includes(word[i])
        ) {
            return false;
        }
    }
    return true;
}

/**
 * Load data when document is ready
 */
document.onreadystatechange = function() {
    if (document.readyState !== "complete") {
        document.querySelector("body").style.visibility = "hidden";
        document.querySelector("#loader").style.visibility = "visible";
    } else {
        initGlobalData(function(wordsData) {
            postProcessWords(wordsData);
            document.querySelector("#loader").style.display = "none";
            document.querySelector("body").style.visibility = "visible";
        });
    }
};

function getCharacters() {
    let domElements = Array.from(document.getElementsByClassName("hex-input"));
    return domElements.map(element => element.value.length > 0 ? element.value[0].toLowerCase() : "");
}

function getRequiredCharacter() {
    let domElement = document.getElementById("center-letter-input");
    if (domElement.value.length > 0) {
        return domElement.value[0].toLowerCase();
    }
    return "";
}


function findSolutions() {
    let characters = getCharacters();
    let keyCharacter = getRequiredCharacter();

    let keyWords = keyCharacter in wordsByCharacter
        ? wordsByCharacter[keyCharacter]
        : [];
    let validWords = keyWords.filter(
        x => x.length > 2 && isWordValid(x, characters));

    let validAffixes = {};
    validWords.forEach(word => {
        validAffixes[word] = []
        wordsAffixes[word].forEach(affix => {
            if (isWordValid(affix, characters)) {
                validAffixes[word].push(affix);
            }
        })        
    });

    return [validWords, validAffixes];
}


function onHexKeyDown(event) {
    if (event.key != "Backspace") {
        if (
            event.srcElement.value.length >= 1 ||
            !/[a-z|ç]/i.test(event.key)
        ) {
            event.preventDefault();
        }
    }
}


document.getElementById("solve-button").onclick = function () {
    let resultsDiv = document.getElementById("solution-list");
    const [validWords, validAffixes] = findSolutions();

    // Clear DOM
    resultsDiv.innerHTML = "";

    // Set solutions
    validWords.forEach(word => {
        const para = document.createElement("p");
        const affixesText = validAffixes[word].join(" | ");
        if (validAffixes[word].length > 0) {
            const node = document.createTextNode(
                word + " | " + affixesText);
            para.appendChild(node);
        } else {
            const node = document.createTextNode(word);
            para.appendChild(node);
        }

        resultsDiv.appendChild(para);
    })
}