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

        renderTopSectorStocks();

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



/* =========================================================
   TOP 2 SECTORS + TOP 10 STOCKS
   ========================================================= */

const TOP_SECTOR_PERIODS = [
    { key: "Daily", label: "Daily" },
    { key: "Weekly", label: "Weekly" },
    { key: "1M", label: "1M" },
    { key: "3M", label: "3M" },
    { key: "6M", label: "6M" },
    { key: "YTD", label: "YTD" }
];

let topSectorPeriod = "Daily";


function renderTopSectorStocks() {

    const existing =
        document.getElementById(
            "topSectorStocksSection"
        );

    if (existing) {
        existing.remove();
    }

    const leadershipSection =
        sectorCards.closest(".section");

    if (!leadershipSection) {
        return;
    }

    const section =
        document.createElement("section");

    section.id =
        "topSectorStocksSection";

    section.className =
        "section top-sector-stocks-section";

    section.innerHTML = `
        <div class="section-heading">
            <div>
                <div class="section-label">
                    LEADERSHIP
                </div>

                <h2>
                    Top 2 Sectors & Top 10 Stocks
                </h2>
            </div>

            <div class="section-note">
                Ranked by average stock return
            </div>
        </div>

        <div class="top-sector-tabs">
            ${TOP_SECTOR_PERIODS
                .map(
                    period => `
                        <button
                            type="button"
                            class="top-sector-tab ${
                                period.key ===
                                topSectorPeriod
                                    ? "active"
                                    : ""
                            }"
                            data-top-period="${period.key}"
                        >
                            ${period.label}
                        </button>
                    `
                )
                .join("")}
        </div>

        <div
            id="topSectorPanels"
            class="top-sector-panels"
        ></div>
    `;

    leadershipSection.insertAdjacentElement(
        "afterend",
        section
    );

    section
        .querySelectorAll(
            ".top-sector-tab"
        )
        .forEach(button => {

            button.addEventListener(
                "click",
                () => {

                    topSectorPeriod =
                        button.dataset.topPeriod;

                    section
                        .querySelectorAll(
                            ".top-sector-tab"
                        )
                        .forEach(tab =>
                            tab.classList.toggle(
                                "active",
                                tab === button
                            )
                        );

                    renderTopSectorPanels();
                }
            );
        });

    injectTopSectorStyles();

    renderTopSectorPanels();
}


function getTopSectorData(periodKey) {

    const sectorMap =
        new Map();

    stocks.forEach(stock => {

        const sector =
            String(
                stock.Sector || ""
            ).trim();

        if (!sector) {
            return;
        }

        const symbol =
            String(
                stock.Symbol || ""
            ).trim();

        if (!symbol) {
            return;
        }

        const value =
            Number(
                stock[periodKey]
            );

        if (
            !Number.isFinite(value)
        ) {
            return;
        }

        const identity =
            String(
                stock["ISIN Code"] ||
                symbol
            ).trim();

        if (!sectorMap.has(sector)) {
            sectorMap.set(
                sector,
                new Map()
            );
        }

        const stockMap =
            sectorMap.get(sector);

        /*
         * One stock must count only once inside a sector.
         * If the source contains duplicate rows for the
         * same stock/index membership, keep the first valid
         * observation.
         */
        if (!stockMap.has(identity)) {
            stockMap.set(
                identity,
                {
                    ...stock,
                    _return: value
                }
            );
        }
    });

    const sectorResults =
        Array.from(
            sectorMap.entries()
        )
        .map(
            ([sector, stockMap]) => {

                const sectorStocks =
                    Array.from(
                        stockMap.values()
                    );

                if (
                    !sectorStocks.length
                ) {
                    return null;
                }

                const average =
                    sectorStocks.reduce(
                        (sum, stock) =>
                            sum +
                            stock._return,
                        0
                    ) /
                    sectorStocks.length;

                const positiveCount =
                    sectorStocks.filter(
                        stock =>
                            stock._return > 0
                    ).length;

                sectorStocks.sort(
                    (a, b) =>
                        b._return -
                        a._return
                );

                return {
                    sector,
                    stocks: sectorStocks,
                    average,
                    positivePct:
                        (
                            positiveCount /
                            sectorStocks.length
                        ) *
                        100
                };
            }
        )
        .filter(Boolean)
        .sort(
            (a, b) =>
                b.average -
                a.average
        );

    return sectorResults.slice(0, 2);
}


function renderTopSectorPanels() {

    const container =
        document.getElementById(
            "topSectorPanels"
        );

    if (!container) {
        return;
    }

    const topSectors =
        getTopSectorData(
            topSectorPeriod
        );

    if (!topSectors.length) {

        container.innerHTML = `
            <div class="top-sector-empty">
                No sector data available.
            </div>
        `;

        return;
    }

    container.innerHTML =
        topSectors
            .map(
                (sector, sectorIndex) =>
                    renderTopSectorPanel(
                        sector,
                        sectorIndex
                    )
            )
            .join("");
}


function renderTopSectorPanel(
    sector,
    sectorIndex
) {

    const medals = [
        "🥇",
        "🥈"
    ];

    const rows =
        sector.stocks
            .slice(0, 10)
            .map(
                (stock, index) => {

                    const value =
                        stock._return;

                    const chartUrl =
                        "https://chartink.com/stocks/" +
                        encodeURIComponent(
                            stock.Symbol
                        ) +
                        ".html";

                    return `
                        <tr>
                            <td class="top-rank">
                                ${index + 1}
                            </td>

                            <td>
                                <a
                                    class="top-stock-symbol"
                                    href="${chartUrl}"
                                    target="_blank"
                                    rel="noopener noreferrer"
                                >
                                    ${escapeHtml(
                                        stock.Symbol
                                    )}
                                </a>
                            </td>

                            <td
                                class="top-company"
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

                            <td
                                class="
                                    numeric
                                    ${
                                        value >= 0
                                            ? "positive"
                                            : "negative"
                                    }
                                "
                            >
                                ${formatPercent(
                                    value
                                )}
                            </td>

                            <td>
                                <a
                                    class="top-chart-link"
                                    href="${chartUrl}"
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    aria-label="Open Chartink chart for ${escapeHtml(
                                        stock.Symbol
                                    )}"
                                >
                                    Chart
                                </a>
                            </td>
                        </tr>
                    `;
                }
            )
            .join("");

    return `
        <div class="top-sector-panel">

            <div class="top-sector-panel-header">

                <div class="top-sector-title-wrap">

                    <div class="top-sector-rank">
                        ${medals[sectorIndex]}
                        #${sectorIndex + 1}
                    </div>

                    <div class="top-sector-name">
                        ${escapeHtml(
                            sector.sector
                        )}
                    </div>

                </div>

                <div class="top-sector-average ${
                    sector.average >= 0
                        ? "positive"
                        : "negative"
                }">
                    ${formatPercent(
                        sector.average
                    )}
                    <span>
                        avg
                    </span>
                </div>

            </div>

            <div class="top-sector-meta">
                <span>
                    ${sector.stocks.length}
                    stocks
                </span>

                <span>
                    ${formatPercent(
                        sector.positivePct
                    )}
                    positive
                </span>
            </div>

            <div class="top-sector-table-wrap">

                <table
                    class="top-sector-table"
                >
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Stock</th>
                            <th>Company</th>
                            <th class="numeric">
                                ${escapeHtml(
                                    topSectorPeriod
                                )}
                            </th>
                            <th></th>
                        </tr>
                    </thead>

                    <tbody>
                        ${rows}
                    </tbody>
                </table>

            </div>

        </div>
    `;
}


function injectTopSectorStyles() {

    if (
        document.getElementById(
            "topSectorStocksStyles"
        )
    ) {
        return;
    }

    const style =
        document.createElement("style");

    style.id =
        "topSectorStocksStyles";

    style.textContent = `
        .top-sector-stocks-section {
            margin-top: 34px;
        }

        .top-sector-tabs {
            display: flex;
            gap: 7px;
            flex-wrap: wrap;
            margin-bottom: 13px;
        }

        .top-sector-tab {
            height: 36px;
            padding: 0 15px;

            border: 1px solid #e2e8f0;
            border-radius: 999px;

            background: #ffffff;
            color: #64748b;

            font-size: 12px;
            font-weight: 700;

            transition:
                background .15s ease,
                color .15s ease,
                border-color .15s ease,
                transform .15s ease;
        }

        .top-sector-tab:hover {
            border-color: #bfdbfe;
            color: #2563eb;
            transform: translateY(-1px);
        }

        .top-sector-tab.active {
            background: #2563eb;
            border-color: #2563eb;
            color: #ffffff;
        }

        .top-sector-panels {
            display: grid;
            grid-template-columns:
                repeat(2, minmax(0, 1fr));
            gap: 14px;
        }

        .top-sector-panel {
            background: #ffffff;
            border: 1px solid #e5eaf1;
            border-radius: 16px;
            overflow: hidden;
            box-shadow:
                0 8px 28px
                rgba(15, 23, 42, .055);
        }

        .top-sector-panel-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 15px;

            padding: 17px 18px 9px;
        }

        .top-sector-title-wrap {
            min-width: 0;
        }

        .top-sector-rank {
            color: #64748b;
            font-size: 10px;
            font-weight: 800;
            margin-bottom: 5px;
        }

        .top-sector-name {
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;

            color: #0f172a;
            font-size: 17px;
            font-weight: 850;
            letter-spacing: -.02em;
        }

        .top-sector-average {
            flex-shrink: 0;

            font-size: 22px;
            font-weight: 850;
            letter-spacing: -.03em;
        }

        .top-sector-average span {
            color: #94a3b8;
            font-size: 10px;
            font-weight: 600;
            letter-spacing: 0;
        }

        .top-sector-meta {
            display: flex;
            justify-content: space-between;

            padding: 0 18px 12px;

            color: #64748b;
            font-size: 11px;
        }

        .top-sector-table-wrap {
            overflow-x: auto;
            border-top: 1px solid #edf1f5;
        }

        .top-sector-table {
            width: 100%;
            min-width: 590px;

            border-collapse: collapse;
            table-layout: fixed;
        }

        .top-sector-table th {
            position: static;

            padding: 8px 10px;

            background: #f8fafc;
            border-bottom: 1px solid #e5eaf1;

            color: #64748b;
            font-size: 9px;
            font-weight: 800;
            text-align: left;
        }

        .top-sector-table td {
            padding: 8px 10px;

            border-bottom: 1px solid #edf1f5;

            color: #334155;
            font-size: 11px;
        }

        .top-sector-table tbody tr:last-child td {
            border-bottom: 0;
        }

        .top-sector-table tbody tr:hover {
            background: #f8fbff;
        }

        .top-sector-table th:first-child,
        .top-sector-table td:first-child {
            width: 34px;
            color: #94a3b8;
        }

        .top-sector-table th:nth-child(2),
        .top-sector-table td:nth-child(2) {
            width: 105px;
        }

        .top-sector-table th:nth-child(3),
        .top-sector-table td:nth-child(3) {
            width: auto;
        }

        .top-sector-table th:nth-child(4),
        .top-sector-table td:nth-child(4) {
            width: 82px;
        }

        .top-sector-table th:nth-child(5),
        .top-sector-table td:nth-child(5) {
            width: 60px;
        }

        .top-stock-symbol {
            color: #059669;
            text-decoration: none;
            font-weight: 850;
        }

        .top-stock-symbol:hover {
            text-decoration: underline;
        }

        .top-company {
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .top-chart-link {
            display: inline-flex;
            align-items: center;
            justify-content: center;

            height: 25px;
            padding: 0 8px;

            border: 1px solid #dbe3ed;
            border-radius: 7px;

            color: #2563eb;
            background: #ffffff;

            text-decoration: none;

            font-size: 9px;
            font-weight: 700;
        }

        .top-chart-link:hover {
            background: #eff6ff;
            border-color: #bfdbfe;
        }

        .top-sector-empty {
            padding: 30px;
            background: #ffffff;
            border: 1px solid #e5eaf1;
            border-radius: 14px;
            color: #64748b;
            text-align: center;
        }

        @media (max-width: 900px) {
            .top-sector-panels {
                grid-template-columns: 1fr;
            }
        }

        @media (max-width: 560px) {
            .top-sector-tabs {
                overflow-x: auto;
                flex-wrap: nowrap;
                padding-bottom: 3px;
            }

            .top-sector-tab {
                flex-shrink: 0;
            }

            .top-sector-panel-header {
                align-items: flex-start;
            }

            .top-sector-average {
                font-size: 18px;
            }
        }
    `;

    document.head.appendChild(style);
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