-- UDP File Transfer Protocol Dissector for Wireshark
-- Plugin para analizar el protocolo de transferencia de archivos UDP
-- Soporta Stop-and-Wait y Go-Back-N

-- Crear el protocolo
local udp_file_transfer = Proto("udpft", "UDP File Transfer Protocol")

-- Definir los campos del protocolo para Stop-and-Wait
local fields = udp_file_transfer.fields
fields.seq_num = ProtoField.uint8("udpft.seq_num", "Sequence Number", base.DEC, nil, 0x02)
fields.flag_end = ProtoField.uint8("udpft.flag_end", "End Flag", base.DEC, {[0]="Data", [1]="End"}, 0x01)
fields.data_len = ProtoField.uint16("udpft.data_len", "Data Length", base.DEC)
fields.data = ProtoField.bytes("udpft.data", "Data")

-- Campos adicionales para Go-Back-N
fields.pkg_id = ProtoField.uint32("udpft.pkg_id", "Package ID", base.DEC)

-- Campo para ACKs
fields.ack_num = ProtoField.uint8("udpft.ack_num", "ACK Number", base.DEC)

-- Campo para identificar el tipo de protocolo
fields.protocol_type = ProtoField.string("udpft.protocol_type", "Protocol Type")

-- Función para determinar si es un paquete de nuestro protocolo
local function is_file_transfer_packet(buffer, pinfo)
    -- Verificar puerto (ajustar según tus puertos)
    if pinfo.src_port == 5005 or pinfo.dst_port == 5005 or 
       pinfo.src_port == 5006 or pinfo.dst_port == 5006 then
        return true
    end
    
    -- Verificar longitud mínima
    if buffer:len() < 1 then
        return false
    end
    
    -- Si es muy corto, probablemente es un ACK
    if buffer:len() == 1 then
        return true
    end
    
    -- Verificar estructura básica
    if buffer:len() >= 3 then
        return true
    end
    
    return false
end

-- Función para determinar el tipo de protocolo
local function detect_protocol_type(buffer)
    local length = buffer:len()
    
    -- ACK packets son de 1 byte
    if length == 1 then
        return "ACK"
    end
    
    -- Handshake packets (texto plano)
    if length > 3 then
        local text = buffer(0, math.min(10, length)):string()
        if text:match("UPLOAD") or text:match("DOWNLOAD") then
            return "HANDSHAKE"
        end
        -- Verificar si parece un nombre de archivo
        if text:match("%.") and not text:match("[%c%z]") then
            return "HANDSHAKE"
        end
    end
    
    -- Stop-and-Wait: header de 3 bytes + datos
    if length >= 3 then
        local first_byte = buffer(0, 1):uint()
        local data_len = buffer(1, 2):uint()
        
        -- Para Stop-and-Wait, verificar si la longitud coincide
        if length == 3 + data_len then
            return "STOP_AND_WAIT"
        end
    end
    
    -- Go-Back-N: header de 7 bytes + datos  
    if length >= 7 then
        local first_byte = buffer(0, 1):uint()
        local data_len = buffer(1, 2):uint()
        
        -- Para Go-Back-N, verificar si la longitud coincide
        if length == 7 + data_len then
            return "GO_BACK_N"
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
    
    -- Detectar tipo de protocolo
    local proto_type = detect_protocol_type(buffer)
    subtree:add(fields.protocol_type, proto_type)
    
    -- Procesar según el tipo
    if proto_type == "ACK" then
        -- Paquete ACK (1 byte)
        local ack_num = buffer(0, 1):uint()
        subtree:add(fields.ack_num, buffer(0, 1))
        pinfo.cols.info = string.format("ACK %d", ack_num)
        
    elseif proto_type == "HANDSHAKE" then
        -- Paquete de handshake (texto plano)
        local text = buffer():string()
        subtree:add("Handshake Data: " .. text)
        pinfo.cols.info = "Handshake: " .. text
        
    elseif proto_type == "STOP_AND_WAIT" then
        -- Paquete Stop-and-Wait
        local first_byte = buffer(0, 1):uint()
        local seq_num = bit.band(bit.rshift(first_byte, 1), 1)
        local flag_end = bit.band(first_byte, 1)
        local data_len = buffer(1, 2):uint()
        
        subtree:add(fields.seq_num, buffer(0, 1))
        subtree:add(fields.flag_end, buffer(0, 1))
        subtree:add(fields.data_len, buffer(1, 2))
        
        if data_len > 0 and length > 3 then
            subtree:add(fields.data, buffer(3, data_len))
        end
        
        local info = string.format("Stop-and-Wait: Seq=%d, End=%d, Len=%d", 
                                 seq_num, flag_end, data_len)
        pinfo.cols.info = info
        
    elseif proto_type == "GO_BACK_N" then
        -- Paquete Go-Back-N
        local first_byte = buffer(0, 1):uint()
        local flag_end = bit.band(first_byte, 1)
        local data_len = buffer(1, 2):uint()
        local pkg_id = buffer(3, 4):uint()
        
        subtree:add(fields.flag_end, buffer(0, 1))
        subtree:add(fields.data_len, buffer(1, 2))
        subtree:add(fields.pkg_id, buffer(3, 4))
        
        if data_len > 0 and length > 7 then
            subtree:add(fields.data, buffer(7, data_len))
        end
        
        local info = string.format("Go-Back-N: ID=%d, End=%d, Len=%d", 
                                 pkg_id, flag_end, data_len)
        pinfo.cols.info = info
        
    else
        -- Paquete desconocido
        subtree:add("Unknown packet format")
        pinfo.cols.info = "Unknown UDP File Transfer packet"
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
    version = "1.0.0",
    author = "UDP File Transfer Protocol Analyzer",
    description = "Dissector for custom UDP file transfer protocol supporting Stop-and-Wait and Go-Back-N"
})
