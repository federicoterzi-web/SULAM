"""Localidades de Tucumán por departamento, para el desplegable «departamento → localidad».

Es una lista de partida, armada a mano con los centros urbanos y comunas rurales más conocidos de cada
departamento; NO es el listado oficial completo. Se completa sola: las localidades que se cargan en legajos,
recursos y contactos aparecen después en el desplegable (ver `routers/general.py`). Para sumar o corregir una de
fábrica, se edita este diccionario. El campo siempre admite escribir una localidad que no esté en la lista.
"""

LOCALIDADES: dict[str, list[str]] = {
    "Burruyacú": ["Burruyacú", "Benjamín Paz", "El Chañar", "Gobernador Garmendia", "Gobernador Piedrabuena", "La Ramada de Abajo", "Villa Padre Monti"],
    "Capital": ["San Miguel de Tucumán"],
    "Chicligasta": ["Concepción", "Alpachiri", "Arcadia", "Gastona", "Medinas", "Alto Verde", "Santa Ana"],
    "Cruz Alta": ["Banda del Río Salí", "Alderetes", "Delfín Gallo", "Colombres", "Los Ralos", "Cruz Alta", "Ranchillos", "Las Cejas", "El Bracho", "San Andrés"],
    "Famaillá": ["Famaillá", "Ingenio Fronterita", "Padilla", "Manuel García Fernández"],
    "Graneros": ["Graneros", "Lamadrid", "Taco Ralo"],
    "Juan Bautista Alberdi": ["Juan Bautista Alberdi", "Villa Belgrano", "Escaba"],
    "La Cocha": ["La Cocha", "Huasa Pampa", "Rumi Punco"],
    "Leales": ["Bella Vista", "Leales", "Los Gutiérrez"],
    "Lules": ["Lules", "San Pablo", "El Manantial", "La Reducción"],
    "Monteros": ["Monteros", "Acheral", "Santa Lucía", "Villa Quinteros", "Soldado Maldonado", "Río Seco"],
    "Río Chico": ["Aguilares", "Río Chico", "Los Sarmientos", "Villa Clara"],
    "Simoca": ["Simoca", "Monteagudo", "Atahona"],
    "Tafí del Valle": ["Tafí del Valle", "El Mollar", "Amaicha del Valle", "Colalao del Valle"],
    "Tafí Viejo": ["Tafí Viejo", "Las Talitas", "El Cadillal", "Los Nogales", "Raco", "Villa Carmela"],
    "Trancas": ["Trancas", "San Pedro de Colalao", "Choromoro", "Tapia", "Vipos"],
    "Yerba Buena": ["Yerba Buena", "Cevil Redondo", "San Javier", "Marcos Paz", "Villa Nougués"],
}
