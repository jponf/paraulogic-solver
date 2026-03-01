
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
        xobj.open('GET', 'data/words_v4.json', true);
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
document.onreadystatechange = function () {
    if (document.readyState !== "complete") {
        document.querySelector("#loader").style.visibility = "visible";
    } else {
        initGlobalData(function (wordsData) {
            postProcessWords(wordsData);
            document.querySelector("#loader").style.display = "none";
            document.querySelector("body").classList.remove("loading");
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
    if (event.key.length == 1) {   // Non-character keys have long names
        if (
            event.target.value.length >= 1 ||
            !/[a-z|ç]/i.test(event.key)
        ) {
            event.preventDefault();
        }
    }
}


// Add event listeners to all hex inputs
const hexInputs = Array.from(document.querySelectorAll(".hex-input"));
const solveButton = document.getElementById("solve-button");
hexInputs.forEach(function (input, index) {
    // Capture event and allow only valid chars
    input.addEventListener("keydown", onHexKeyDown);
    // Focus on next hex input
    input.addEventListener("input", function () {
        if (input.value.length === 1 && /[a-zç]/i.test(input.value)) {
            if (index < hexInputs.length - 1) {
                hexInputs[index + 1].focus();
            } else {
                solveButton.focus();
            }
        }
    });
});

/**
 * Fetch today's characters from the original Paraulogic game.
 */
async function loadTodayCharacters() {
    const PARAULOGIC_URL = "https://www.vilaweb.cat/paraulogic/";
    const CORS_PROXY = "https://corsproxy.io/?";

    try {
        const response = await fetch(CORS_PROXY + encodeURIComponent(PARAULOGIC_URL));
        if (!response.ok) {
            throw new Error(`HTTP error: ${response.status}`);
        }

        const html = await response.text();

        // Find today's letters in var t={"l":[...]} (not var y which is yesterday's)
        const startMarker = 'var t={"l":[';
        const startIndex = html.indexOf(startMarker);
        if (startIndex === -1) {
            throw new Error("No s'han trobat les lletres d'avui");
        }

        const arrayStart = startIndex + startMarker.length - 1; // include the '['
        const arrayEnd = html.indexOf(']', arrayStart) + 1;
        const arrayStr = html.substring(arrayStart, arrayEnd);

        const characters = JSON.parse(arrayStr);

        if (!characters || characters.length < 6) {
            throw new Error("Format de lletres invàlid");
        }
        console.log("Characters:", characters)
        // First letter is the center (required), rest are surrounding
        const hexInputs = Array.from(document.querySelectorAll(".hex-input"));
        hexInputs.forEach(input => input.value = "");
        // Center letter goes to index 3 (the center hex input)
        hexInputs[3].value = characters[0].toUpperCase();
        // Remaining letters fill the other positions
        let inputIndex = 0;
        for (let i = 1; i < characters.length; i++) {
            if (inputIndex === 3) inputIndex++; // Skip center position
            hexInputs[inputIndex].value = characters[i].toUpperCase();
            inputIndex++;
        }

        // Focus on solve button for quick action
        document.getElementById("solve-button").focus();

    } catch (error) {
        console.error("Error loading today's characters:", error);
        alert("Error carregant les lletres: " + error.message);
    }
}

document.getElementById("load-today-button").onclick = loadTodayCharacters;

/**
 * Fetch today's solutions from the original Paraulogic game.
 */
async function loadTodaySolutions() {
    const PARAULOGIC_URL = "https://www.vilaweb.cat/paraulogic/";
    const CORS_PROXY = "https://corsproxy.io/?";

    try {
        const response = await fetch(CORS_PROXY + encodeURIComponent(PARAULOGIC_URL));
        if (!response.ok) {
            throw new Error(`HTTP error: ${response.status}`);
        }

        const html = await response.text();

        // Find today's solutions in var t={"l":[...],"p":{...}}
        const startMarker = 'var t={"l":[';
        const startIndex = html.indexOf(startMarker);
        if (startIndex === -1) {
            throw new Error("No s'han trobat les solucions d'avui");
        }

        // Find the "p": object within var t
        const pMarker = ',"p":{';
        const pIndex = html.indexOf(pMarker, startIndex);
        if (pIndex === -1) {
            throw new Error("No s'han trobat les solucions");
        }

        // Extract the solutions object - find matching closing brace
        const objStart = pIndex + pMarker.length - 1; // include the '{'
        let braceCount = 1;
        let objEnd = objStart + 1;
        while (braceCount > 0 && objEnd < html.length) {
            if (html[objEnd] === '{') braceCount++;
            else if (html[objEnd] === '}') braceCount--;
            objEnd++;
        }

        const objStr = html.substring(objStart, objEnd);
        const solutions = JSON.parse(objStr);
        const solutionWords = Object.keys(solutions).sort();

        // Display solutions in the official section
        const resultsCountPar = document.getElementById("official-solution-count");
        const resultsDiv = document.getElementById("official-solution-list");

        resultsCountPar.innerHTML = "Solucions oficials: " + solutionWords.length;
        resultsDiv.innerHTML = "";

        solutionWords.forEach(word => {
            const para = document.createElement("p");
            para.appendChild(document.createTextNode(word));
            resultsDiv.appendChild(para);
        });

    } catch (error) {
        console.error("Error loading today's solutions:", error);
        alert("Error carregant les solucions: " + error.message);
    }
}

document.getElementById("load-solutions-button").onclick = loadTodaySolutions;

document.getElementById("solve-button").onclick = function () {
    let resultsCountPar = document.getElementById("solution-count");
    let resultsDiv = document.getElementById("solution-list");
    const [validWords, validAffixes] = findSolutions();

    // Clear DOM
    resultsCountPar.innerHTML = "";
    resultsDiv.innerHTML = "";

    // Count solutions
    let resultsCount = validWords.reduce(
        (total, current) => total + validAffixes[current].length,
        validWords.length)
    resultsCountPar.innerHTML = "Solucions trobades: " + resultsCount

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