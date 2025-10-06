-- UDP File Transfer Protocol Dissector for Wireshark
-- Plugin para analizar el protocolo de transferencia de archivos UDP
-- Soporta Stop-and-Wait y Go-Back-N

-- Crear el protocolo
local udp_file_transfer = Proto("udpft", "UDP File Transfer Protocol")

-- Definir los campos del protocolo
local fields = udp_file_transfer.fields
fields.flag_end = ProtoField.uint8("udpft.flag_end", "End Flag", base.DEC, {[0]="Data", [1]="Last"}, 0x01)
fields.data_len = ProtoField.uint16("udpft.data_len", "Data Length", base.DEC)
fields.pkg_id = ProtoField.uint32("udpft.pkg_id", "Package ID", base.DEC)
fields.data = ProtoField.bytes("udpft.data", "Data")
fields.ack_num = ProtoField.uint32("udpft.ack_num", "ACK Number", base.DEC)
fields.handshake = ProtoField.string("udpft.handshake", "Handshake Data")

-- Función para determinar si es un paquete de nuestro protocolo
local function is_file_transfer_packet(buffer, pinfo)
    -- Verificar puertos
    if pinfo.src_port == 5005 or pinfo.dst_port == 5005 or 
       pinfo.src_port == 5006 or pinfo.dst_port == 5006 then
        return true
    end
    return false
end

-- Función para verificar si es texto ASCII imprimible
local function is_printable_text(buffer)
    local length = buffer:len()
    if length == 0 or length > 256 then
        return false
    end
    
    local printable_count = 0
    for i = 0, length - 1 do
        local byte = buffer(i, 1):uint()
        -- ASCII imprimible: 32-126, o newline/CR
        if (byte >= 32 and byte <= 126) or byte == 10 or byte == 13 then
            printable_count = printable_count + 1
        end
    end
    
    -- Si más del 90% son caracteres imprimibles, es texto
    return printable_count > (length * 0.9)
end

-- Función para determinar el tipo de paquete
local function detect_packet_type(buffer)
    local length = buffer:len()
    
    -- ACK: exactamente 4 bytes
    if length == 4 then
        return "ACK"
    end
    
    -- Handshake: texto corto (1-256 bytes) que contiene comandos o nombres de archivo
    if length >= 1 and length <= 256 and is_printable_text(buffer) then
        local text = buffer():string()
        
        -- Paso 1: U o D (1 byte)
        if length == 1 and (text == "U" or text == "D") then
            return "HANDSHAKE_TYPE"
        end
        
        -- Paso 2: SW o GBN (2-3 bytes)
        if length <= 3 and (text == "SW" or text == "GBN") then
            return "HANDSHAKE_PROTOCOL"
        end
        
        -- Paso 3: nombre de archivo
        if length > 3 then
            return "HANDSHAKE_FILENAME"
        end
        
        return "HANDSHAKE"
    end
    
    -- Paquetes de datos: header de 7 bytes + datos (0-1000 bytes)
    if length >= 7 then
        local data_len = buffer(1, 2):uint()
        
        -- Verificar si el tamaño coincide: 7 bytes header + data_len
        if length == 7 + data_len then
            return "DATA"
        end
        
        -- Si está cerca (tolerancia de ±10 bytes por red overhead), también aceptar
        if math.abs(length - (7 + data_len)) <= 10 then
            return "DATA"
        end
    end
    
    return "UNKNOWN"
end

-- Función principal del dissector
function udp_file_transfer.dissector(buffer, pinfo, tree)
    local length = buffer:len()
    
    -- Verificar si es nuestro protocolo
    if not is_file_transfer_packet(buffer, pinfo) then
        return 0
    end
    
    -- Cambiar el protocolo mostrado en Wireshark
    pinfo.cols.protocol = udp_file_transfer.name
    
    -- Crear el árbol del protocolo
    local subtree = tree:add(udp_file_transfer, buffer(), "UDP File Transfer Protocol")
    
    -- Detectar tipo de paquete
    local pkt_type = detect_packet_type(buffer)
    
    -- Procesar según el tipo
    if pkt_type == "ACK" then
        -- Paquete ACK (4 bytes)
        local ack_num = buffer(0, 4):uint()
        subtree:add(fields.ack_num, buffer(0, 4))
        pinfo.cols.info = string.format("ACK %d", ack_num)
        
    elseif pkt_type == "HANDSHAKE_TYPE" then
        -- Handshake paso 1: tipo de operación
        local text = buffer():string()
        subtree:add(fields.handshake, buffer())
        
        if text == "U" then
            pinfo.cols.info = "Handshake: Upload Request"
        elseif text == "D" then
            pinfo.cols.info = "Handshake: Download Request"
        else
            pinfo.cols.info = "Handshake: " .. text
        end
        
    elseif pkt_type == "HANDSHAKE_PROTOCOL" then
        -- Handshake paso 2: protocolo
        local text = buffer():string()
        subtree:add(fields.handshake, buffer())
        
        if text == "SW" then
            pinfo.cols.info = "Handshake: Stop-and-Wait Protocol"
        elseif text == "GBN" then
            pinfo.cols.info = "Handshake: Go-Back-N Protocol"
        else
            pinfo.cols.info = "Handshake: " .. text
        end
        
    elseif pkt_type == "HANDSHAKE_FILENAME" then
        -- Handshake paso 3: nombre de archivo
        local text = buffer():string()
        subtree:add(fields.handshake, buffer())
        pinfo.cols.info = "Handshake: " .. text
        
    elseif pkt_type == "HANDSHAKE" then
        -- Handshake genérico
        local text = buffer():string()
        subtree:add(fields.handshake, buffer())
        pinfo.cols.info = "Handshake: " .. text
        
    elseif pkt_type == "DATA" then
        -- Paquete de datos (7 bytes header + datos)
        local first_byte = buffer(0, 1):uint()
        local flag_end = bit.band(first_byte, 1)
        local data_len = buffer(1, 2):uint()
        local pkg_id = buffer(3, 4):uint()
        
        subtree:add(fields.flag_end, buffer(0, 1))
        subtree:add(fields.data_len, buffer(1, 2))
        subtree:add(fields.pkg_id, buffer(3, 4))
        
        if data_len > 0 and length > 7 then
            local actual_data_len = math.min(data_len, length - 7)
            subtree:add(fields.data, buffer(7, actual_data_len))
        end
        
        -- Determinar si es el último paquete
        local pkt_status = (flag_end == 1) and "LAST" or "DATA"
        
        pinfo.cols.info = string.format("%s: ID=%d, Len=%d bytes", 
                                        pkt_status, pkg_id, data_len)
        
    else
        -- Paquete desconocido
        subtree:add("Unknown packet format")
        pinfo.cols.info = string.format("Unknown packet (%d bytes)", length)
    end
    
    -- Indicar que consumimos todo el buffer
    return length
end

-- Registrar el dissector en los puertos UDP
local udp_port = DissectorTable.get("udp.port")
udp_port:add(5005, udp_file_transfer)  -- Puerto del servidor
udp_port:add(5006, udp_file_transfer)  -- Puerto del cliente

-- También registrar como heurístico para capturar todos los paquetes relevantes
udp_file_transfer:register_heuristic("udp", function(buffer, pinfo, tree)
    if is_file_transfer_packet(buffer, pinfo) then
        udp_file_transfer.dissector(buffer, pinfo, tree)
        return true
    end
    return false
end)

-- Información del plugin
set_plugin_info({
    version = "1.2.0",
    author = "UDP File Transfer Protocol Analyzer",
    description = "Dissector for custom UDP file transfer protocol supporting Stop-and-Wait and Go-Back-N"
})