const STOCK_URL = "data/stock_rs.json";
const SECTOR_URL = "data/sector_summary.json";

let stocks = [];
let sectors = [];

let filteredStocks = [];

let sortColumn = "RS";
let sortDirection = "desc";

const stockCount = document.getElementById("stockCount");
const sectorCount = document.getElementById("sectorCount");
const dataStatus = document.getElementById("dataStatus");

const sectorCards =
    document.getElementById("sectorCards");

const stockTableBody =
    document.getElementById("stockTableBody");

const sectorFilter =
    document.getElementById("sectorFilter");

const periodFilter =
    document.getElementById("periodFilter");

const searchInput =
    document.getElementById("searchInput");

const resultCount =
    document.getElementById("resultCount");

const lastUpdated =
    document.getElementById("lastUpdated");


async function loadData() {

    try {

        const cacheBust =
            "?v=" + Date.now();

        const [
            stockResponse,
            sectorResponse
        ] = await Promise.all([
            fetch(
                STOCK_URL + cacheBust
            ),
            fetch(
                SECTOR_URL + cacheBust
            )
        ]);

        if (!stockResponse.ok) {
            throw new Error(
                "Unable to load stock data"
            );
        }

        if (!sectorResponse.ok) {
            throw new Error(
                "Unable to load sector data"
            );
        }

        stocks =
            await stockResponse.json();

        sectors =
            await sectorResponse.json();

        const uniqueStockCount =
          new Set(
           stocks.map(stock =>
            stock["ISIN Code"] ||
            stock.Symbol
           )
        ).size;

        stockCount.textContent =
          uniqueStockCount.toLocaleString();

        sectorCount.textContent =
            sectors.length;

        dataStatus.textContent =
            "Live";

        dataStatus.classList.add(
            "positive"
        );

        updateDate();

        buildSectorFilter();

        renderSectorCards();

        applyFilters();

    } catch (error) {

        console.error(error);

        dataStatus.textContent =
            "Error";

        dataStatus.classList.add(
            "negative"
        );

        sectorCards.innerHTML = `
            <div class="loading">
                Unable to load dashboard data.
                <br>
                ${escapeHtml(error.message)}
            </div>
        `;

        stockTableBody.innerHTML = `
            <tr>
                <td
                    colspan="12"
                    class="loading"
                >
                    Unable to load stock data.
                </td>
            </tr>
        `;
    }
}


function updateDate() {

    const now = new Date();

    lastUpdated.textContent =
        "Dashboard data • " +
        now.toLocaleString(
            "en-IN",
            {
                dateStyle: "medium",
                timeStyle: "short"
            }
        );
}


function buildSectorFilter() {

    sectorFilter.innerHTML = `
        <option value="ALL">
            All Index / Sectors
        </option>
    `;

    sectors.forEach(
        sector => {

            const name =
                sector["Index / Sector"];

            if (!name) {
                return;
            }

            const option =
                document.createElement(
                    "option"
                );

            option.value = name;

            option.textContent = name;

            sectorFilter.appendChild(
                option
            );
        }
    );
}


function renderSectorCards() {

    sectorCards.innerHTML = "";

    sectors
        .slice(0, 10)
        .forEach(
            (sector, index) => {

                const rs =
                    Number(
                        sector[
                            "Average RS 3M"
                        ]
                    );

                const positive =
                    Number(
                        sector[
                            "Positive RS %"
                        ]
                    );

                const card =
                    document.createElement(
                        "div"
                    );

                card.className =
                    "sector-card";

                card.innerHTML = `
                    <div class="sector-rank">
                        #${index + 1}
                    </div>

                    <div class="sector-name">
                        ${escapeHtml(
                            sector[
                                "Index / Sector"
                            ]
                        )}
                    </div>

                    <div class="
                        sector-rs
                        ${valueClass(rs)}
                    ">
                        ${formatPercent(rs)}
                    </div>

                    <div class="sector-meta">
                        <span>
                            ${sector.Stocks}
                            stocks
                        </span>

                        <span>
                            ${formatPercent(
                                positive
                            )} positive
                        </span>
                    </div>

                    <div class="sector-meta">
                        <span>
                            Top:
                            ${escapeHtml(
                                sector[
                                    "Top Stock"
                                ] || "—"
                            )}
                        </span>

                        <span class="
                            ${valueClass(
                                Number(
                                    sector[
                                        "Top Stock RS"
                                    ]
                                )
                            )}
                        ">
                            ${formatPercent(
                                Number(
                                    sector[
                                        "Top Stock RS"
                                    ]
                                )
                            )}
                        </span>
                    </div>
                `;

                card.addEventListener(
                    "click",
                    () => {

                        sectorFilter.value =
                            sector[
                                "Index / Sector"
                            ];

                        applyFilters();

                        window.scrollTo({
                            top:
                                document
                                .querySelector(
                                    ".filters"
                                )
                                .offsetTop - 20,

                            behavior: "smooth"
                        });
                    }
                );

                sectorCards.appendChild(
                    card
                );
            }
        );
}


function getAllStockSectors(stock) {

    const isin =
        stock["ISIN Code"];

    const symbol =
        stock.Symbol;


    const memberships =
        stocks
            .filter(row => {

                if (
                    isin &&
                    row["ISIN Code"]
                ) {

                    return (
                        row["ISIN Code"] ===
                        isin
                    );

                }

                return (
                    row.Symbol ===
                    symbol
                );

            })
            .map(
                row => row.Sector
            )
            .filter(Boolean);


    return [
        ...new Set(memberships)
    ];
}


function applyFilters() {

    const search =
        searchInput.value
            .trim()
            .toLowerCase();

    const selectedSector =
        sectorFilter.value;


    // --------------------------------------------------
    // STEP 1
    // Apply sector + search filters to original rows
    // --------------------------------------------------

    let matchingRows =
        stocks.filter(stock => {

            const symbol =
                String(
                    stock.Symbol || ""
                ).toLowerCase();

            const company =
                String(
                    stock["Company Name"] || ""
                ).toLowerCase();

            const sector =
                String(
                    stock.Sector || ""
                );

            const matchesSearch =
                !search ||
                symbol.includes(search) ||
                company.includes(search);

            const matchesSector =
                selectedSector === "ALL" ||
                sector === selectedSector;

            return (
                matchesSearch &&
                matchesSector
            );
        });


    // --------------------------------------------------
    // STEP 2
    // Combine duplicate stock memberships
    //
    // Example:
    // AEGISLOG niftyenergy
    // AEGISLOG niftyoilgas
    // AEGISLOG nifty500
    //
    // becomes ONE stock row.
    // --------------------------------------------------

    const stockMap = new Map();


    matchingRows.forEach(stock => {

        const key =
            stock["ISIN Code"] ||
            stock.Symbol;

        if (!key) {
            return;
        }


        if (!stockMap.has(key)) {

            stockMap.set(
                key,
                {
                    ...stock,

                    _sectors: new Set(
                        getAllStockSectors(stock)
                   )
                }
            );

        } else {

            const existing =
                stockMap.get(key);

            if (stock.Sector) {

                existing._sectors.add(
                    stock.Sector
                );

            }

        }

    });


    filteredStocks =
        Array.from(
            stockMap.values()
        ).map(stock => {

            return {
                ...stock,

                Sector:
                    Array.from(
                        stock._sectors
                    ).join(" • ")
            };

        });


    sortStocks();

    renderStockTable();
}

function sortStocks() {

    filteredStocks.sort(
        (a, b) => {

            let aValue;
            let bValue;

            if (sortColumn === "RS") {

                aValue =
                    Number(
                        a[
                            "Stock Relative Strength vs Nifty"
                        ]
                    );

                bValue =
                    Number(
                        b[
                            "Stock Relative Strength vs Nifty"
                        ]
                    );

            } else {

                aValue =
                    Number(
                        a[sortColumn]
                    );

                bValue =
                    Number(
                        b[sortColumn]
                    );
            }

            if (
                Number.isNaN(aValue)
            ) {
                aValue = -Infinity;
            }

            if (
                Number.isNaN(bValue)
            ) {
                bValue = -Infinity;
            }

            if (
                aValue === bValue
            ) {
                return 0;
            }

            const result =
                aValue > bValue
                    ? 1
                    : -1;

            return sortDirection === "asc"
                ? result
                : -result;
        }
    );
}


function renderStockTable() {

    const limit = 250;

    const rows =
        filteredStocks.slice(
            0,
            limit
        );

    if (!rows.length) {

        stockTableBody.innerHTML = `
            <tr>
                <td
                    colspan="12"
                    class="loading"
                >
                    No stocks match
                    your filters.
                </td>
            </tr>
        `;

        resultCount.textContent =
            "0 stocks";

        return;
    }

    stockTableBody.innerHTML =
        rows
            .map(
                (stock, index) => {

                    const rs =
                        Number(
                            stock[
                                "Stock Relative Strength vs Nifty"
                            ]
                        );

                    const chartUrl =
                        "https://chartink.com/stocks/" +
                        encodeURIComponent(
                            stock.Symbol
                        ) +
                        ".html";

                    return `
                        <tr>

                            <td>
                                ${index + 1}
                            </td>

                            <td>
                                <span class="
                                    stock-symbol
                                    ${valueClass(
                                        rs
                                    )}
                                ">
                                    ${escapeHtml(
                                        stock.Symbol
                                    )}
                                </span>
                            </td>

                            <td
                                class="company-name"
                                title="${escapeHtml(
                                    stock[
                                        "Company Name"
                                    ] || ""
                                )}"
                            >
                                ${escapeHtml(
                                    stock[
                                        "Company Name"
                                    ] || "—"
                                )}
                            </td>

                            <td>
                                <span class="
                                    sector-tag
                                ">
                                    ${escapeHtml(
                                        stock.Sector
                                    )}
                                </span>
                            </td>

                            <td class="numeric">
                                ${formatPercent(
                                    Number(
                                        stock.Daily
                                    )
                                )}
                            </td>

                            <td class="numeric">
                                ${formatPercent(
                                    Number(
                                        stock.Weekly
                                    )
                                )}
                            </td>

                            <td class="numeric">
                                ${formatPercent(
                                    Number(
                                        stock["1M"]
                                    )
                                )}
                            </td>

                            <td class="numeric">
                                ${formatPercent(
                                    Number(
                                        stock["3M"]
                                    )
                                )}
                            </td>

                            <td class="numeric">
                                ${formatPercent(
                                    Number(
                                        stock["6M"]
                                    )
                                )}
                            </td>

                            <td class="numeric">
                                ${formatPercent(
                                    Number(
                                        stock.YTD
                                    )
                                )}
                            </td>

                            <td class="
                                numeric
                                ${valueClass(rs)}
                            ">
                                <strong>
                                    ${formatPercent(
                                        rs
                                    )}
                                </strong>
                            </td>

                            <td>
                                <a
                                    class="chart-link"
                                    href="${chartUrl}"
                                    target="_blank"
                                    rel="noopener noreferrer"
                                >
                                    Chart
                                </a>
                            </td>

                        </tr>
                    `;
                }
            )
            .join("");

    if (
        filteredStocks.length > limit
    ) {

        resultCount.textContent =
            `Showing ${limit.toLocaleString()} of ` +
            `${filteredStocks.length.toLocaleString()} stocks`;

    } else {

        resultCount.textContent =
            `${filteredStocks.length.toLocaleString()} stocks`;
    }
}


function formatPercent(value) {

    if (
        value === null ||
        value === undefined ||
        Number.isNaN(value) ||
        !Number.isFinite(value)
    ) {
        return "—";
    }

    const sign =
        value > 0
            ? "+"
            : "";

    return (
        sign +
        value.toFixed(2) +
        "%"
    );
}


function valueClass(value) {

    if (
        value === null ||
        value === undefined ||
        Number.isNaN(value) ||
        !Number.isFinite(value)
    ) {
        return "";
    }

    if (value > 0) {
        return "positive";
    }

    if (value < 0) {
        return "negative";
    }

    return "";
}


function escapeHtml(value) {

    return String(value)
        .replace(
            /&/g,
            "&amp;"
        )
        .replace(
            /</g,
            "&lt;"
        )
        .replace(
            />/g,
            "&gt;"
        )
        .replace(
            /"/g,
            "&quot;"
        )
        .replace(
            /'/g,
            "&#039;"
        );
}


document
    .querySelectorAll(
        "th.sortable"
    )
    .forEach(
        header => {

            header.addEventListener(
                "click",
                () => {

                    const column =
                        header.dataset.sort;

                    if (
                        sortColumn ===
                        column
                    ) {

                        sortDirection =
                            sortDirection ===
                            "desc"
                                ? "asc"
                                : "desc";

                    } else {

                        sortColumn =
                            column;

                        sortDirection =
                            "desc";
                    }

                    sortStocks();

                    renderStockTable();
                }
            );
        }
    );


searchInput.addEventListener(
    "input",
    applyFilters
);


sectorFilter.addEventListener(
    "change",
    applyFilters
);


periodFilter.addEventListener(
    "change",
    () => {

        const period =
            periodFilter.value;

        if (period === "RS") {

            sortColumn = "RS";

        } else {

            sortColumn = period;

        }

        sortDirection = "desc";

        applyFilters();
    }
);


document
    .getElementById(
        "clearFilters"
    )
    .addEventListener(
        "click",
        () => {

            searchInput.value = "";

            sectorFilter.value =
                "ALL";

            periodFilter.value =
                "RS";

            sortColumn = "RS";

            sortDirection = "desc";

            applyFilters();
        }
    );


loadData();