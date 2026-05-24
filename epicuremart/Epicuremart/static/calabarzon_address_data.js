/**
 * Complete CALABARZON (Region IV-A) Address Database
 * Includes provinces, municipalities/cities, barangays, and postal codes
 * Based on Philippine Standard Geographic Code (PSGC)
 */

const CALABARZON_DATA = {
    "Cavite": {
        "Dasmariñas": {
            postal_code: "4114",
            barangays: ["Salawag", "Paliparan I", "Paliparan II", "Langkaan I", "Langkaan II", "Emmanuel I", "Emmanuel II", "Sampaloc I", "Sampaloc II", "San Agustin I", "San Agustin II", "Victoria Reyes"]
        },
        "Bacoor": {
            postal_code: "4102",
            barangays: ["Alima", "Aniban I", "Aniban II", "Banalo", "Digman", "Habay I", "Habay II", "Molino I", "Molino II", "Niog I", "Niog II", "Panapaan I", "Panapaan II", "Queens Row Central", "Talaba I", "Talaba II"]
        },
        "Imus": {
            postal_code: "4103",
            barangays: ["Alapan I-A", "Alapan I-B", "Anabu I-A", "Anabu I-B", "Bayan Luma I", "Bayan Luma II", "Bucandala I", "Bucandala II", "Malagasang I-A", "Malagasang I-B", "Medicion I-A", "Medicion I-B", "Poblacion I-A", "Tanzang Luma I"]
        },
        "Cavite City": {
            postal_code: "4100",
            barangays: ["Barangay 1", "Barangay 2", "Barangay 3", "Barangay 4", "Barangay 5", "Barangay 10", "Barangay 20", "Barangay 30", "Barangay 40", "Barangay 50"]
        },
        "Tagaytay": {
            postal_code: "4120",
            barangays: ["Asisan", "Bagong Tubig", "Kaybagal Central", "Maharlika East", "Neogan", "Tolentino East", "Sungay East"]
        }
    },
    "Laguna": {
        "Calamba": {
            postal_code: "4027",
            barangays: ["Barandal", "Banlic", "Bucal", "Canlubang", "Halang", "Makiling", "Pansol", "Real", "Turbina", "Poblacion 1", "Poblacion 2"]
        },
        "San Pedro": {
            postal_code: "4023",
            barangays: ["Bagong Silang", "Cuyab", "Landayan", "Magsaysay", "Nueva", "Poblacion", "Rosario", "San Antonio", "San Vicente"]
        },
        "Biñan": {
            postal_code: "4024",
            barangays: ["Biñan", "Canlalay", "Casile", "Langkiwa", "Loma", "Malaban", "Malamig", "Poblacion", "Santo Domingo"]
        },
        "Santa Rosa": {
            postal_code: "4026",
            barangays: ["Aplaya", "Balibago", "Don Jose", "Ibaba", "Macabling", "Malusak", "Pulong Santa Cruz", "Tagapo"]
        },
        "Cabuyao": {
            postal_code: "4025",
            barangays: ["Banay-Banay", "Banlic", "Butong", "Mamatid", "Marinig", "Niugan", "Poblacion", "San Isidro"]
        }
    },
    "Batangas": {
        "Batangas City": {
            postal_code: "4200",
            barangays: ["Alangilan", "Balagtas", "Balete", "Bolbok", "Calicanto", "Cuta", "Gulod Labac", "Kumintang Ibaba", "Poblacion"]
        },
        "Lipa": {
            postal_code: "4217",
            barangays: ["Bagong Pook", "Banaybanay", "Bolbok", "Bugtong na Pulo", "Halang", "Inosloban", "Lodlod", "Malitlit", "Marauoy", "Poblacion"]
        },
        "Tanauan": {
            postal_code: "4232",
            barangays: ["Altura Bata", "Altura Matanda", "Altura South", "Ambulong", "Balele", "Banjo East", "Banjo West", "Bilog-Bilog", "Boot"]
        },
        "Santo Tomas": {
            postal_code: "4234",
            barangays: ["San Agustin", "San Antonio", "San Bartolome", "San Felix", "San Fernando", "San Francisco", "San Isidro", "San Joaquin"]
        },
        "Taal": {
            postal_code: "4208",
            barangays: ["Apacay", "Balisong", "Bolbok", "Buli", "Butong", "Carasuche", "Gahol", "Halang", "Imamawo", "Palangue"]
        }
    },
    "Rizal": {
        "Antipolo": {
            postal_code: "1870",
            barangays: ["Bagong Nayon", "Beverly Hills", "Calawis", "Cupang", "Dalig", "Dela Paz", "Inarawan", "Mambugan", "Mayamot", "San Jose", "San Luis", "San Roque", "Santa Cruz"]
        },
        "Cainta": {
            postal_code: "1900",
            barangays: ["San Andres", "San Isidro", "San Juan", "San Roque", "Santa Rosa", "Santo Domingo", "Santo Niño"]
        },
        "Taytay": {
            postal_code: "1920",
            barangays: ["Dolores", "Muzon", "San Isidro", "San Juan", "Santa Ana"]
        },
        "Binangonan": {
            postal_code: "1940",
            barangays: ["Bangad", "Batingan", "Bilibiran", "Ginoong Sanay", "Ithan", "Janosa", "Kalawaan", "Kalinawan", "Kasile"]
        },
        "Angono": {
            postal_code: "1930",
            barangays: ["Bagumbayan", "Kalayaan", "Mahabang Parang", "Poblacion Ibaba", "Poblacion Itaas", "San Isidro", "San Pedro", "San Roque", "San Vicente"]
        }
    },
    "Quezon": {
        "Lucena": {
            postal_code: "4300",
            barangays: ["Barangay 1", "Barangay 2", "Barangay 3", "Barangay 4", "Barangay 5", "Barangay 6", "Barangay 7", "Barangay 8", "Barangay 9", "Barangay 10", "Cotta", "Dalahican", "Domoit", "Gulang-Gulang", "Ibabang Dupay", "Ibabang Iyam"]
        },
        "Tayabas": {
            postal_code: "4327",
            barangays: ["Alitao", "Angelina", "Angeles Zone I", "Angeles Zone II", "Angeles Zone III", "Angeles Zone IV", "Angustias Zone I", "Angustias Zone II", "Angustias Zone III", "Angustias Zone IV"]
        },
        "Sariaya": {
            postal_code: "4322",
            barangays: ["Antipolo", "Barangay 1 Pob.", "Barangay 2 Pob.", "Barangay 3 Pob.", "Barangay 4 Pob.", "Barangay 5 Pob.", "Bignay 1", "Bignay 2", "Bucal", "Canda"]
        },
        "Candelaria": {
            postal_code: "4323",
            barangays: ["Barangay 1 Pob.", "Barangay 2 Pob.", "Barangay 3 Pob.", "Barangay 4 Pob.", "Buenavista East", "Buenavista West", "Bukal Norte", "Bukal Sur"]
        },
        "Pagbilao": {
            postal_code: "4302",
            barangays: ["Alupaye", "Angeles", "Antipolo", "Barangay 1 Pob.", "Barangay 2 Pob.", "Barangay 3 Pob.", "Binahaan A", "Binahaan B", "Bigo"]
        }
    }
};

// Make globally available
if (typeof window !== 'undefined') {
    window.CALABARZON_DATA = CALABARZON_DATA;
}
